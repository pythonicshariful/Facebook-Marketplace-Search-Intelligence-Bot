"""Application configuration loaded from environment variables / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    BASE_DIR = BASE_DIR
    DATA_DIR = Path(os.getenv("FMBOT_DATA_DIR") or BASE_DIR / "data")
    LOG_DIR = Path(os.getenv("FMBOT_LOG_DIR") or BASE_DIR / "logs")

    SECRET_KEY = os.getenv("SECRET_KEY", "")
    FERNET_KEY = os.getenv("FMBOT_FERNET_KEY", "")
    LOG_LEVEL = os.getenv("FMBOT_LOG_LEVEL", "INFO").upper()

    HOST = os.getenv("FMBOT_HOST", "127.0.0.1")
    PORT = _int("FMBOT_PORT", 8080)

    CHROME_BINARY = os.getenv("CHROME_BINARY", "")
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "")
    CHROME_VERSION_MAIN = _int("CHROME_VERSION_MAIN", 0)

    SCHEDULER_ENABLED = _bool("FMBOT_SCHEDULER_ENABLED", True)
    SCHEDULER_TICK_SECONDS = max(5, _int("FMBOT_SCHEDULER_TICK_SECONDS", 15))

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Tampermonkey / Scraper mode
    SCRAPER_MODE = os.getenv("FMBOT_SCRAPER_MODE", "tampermonkey").lower()  # tampermonkey | selenium
    TM_API_TOKEN = os.getenv("FMBOT_TM_API_TOKEN", "fb-marketplace-tm-token-secret")

    # Flask / security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # token valid for the session lifetime
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("FMBOT_SECURE_COOKIES", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    TESTING = False

    def __init__(self) -> None:
        self.DATABASE_URL = os.getenv("DATABASE_URL") or (
            f"sqlite:///{(self.DATA_DIR / 'app.db').as_posix()}"
        )

    # Derived paths
    @property
    def PROFILES_DIR(self) -> Path:
        return self.DATA_DIR / "browser_profiles"

    @property
    def LOCKS_DIR(self) -> Path:
        return self.DATA_DIR / "locks"

    @property
    def BACKUP_DIR(self) -> Path:
        return self.DATA_DIR / "backups"

    @property
    def EXPORT_DIR(self) -> Path:
        return self.DATA_DIR / "exports"

    def ensure_dirs(self) -> None:
        for p in (self.DATA_DIR, self.LOG_DIR, self.PROFILES_DIR, self.LOCKS_DIR,
                  self.BACKUP_DIR, self.EXPORT_DIR):
            Path(p).mkdir(parents=True, exist_ok=True)

    def to_flask(self) -> dict:
        keys = ["SECRET_KEY", "WTF_CSRF_ENABLED", "WTF_CSRF_TIME_LIMIT", "SESSION_COOKIE_HTTPONLY",
                "SESSION_COOKIE_SAMESITE", "SESSION_COOKIE_SECURE", "REMEMBER_COOKIE_HTTPONLY",
                "REMEMBER_COOKIE_SECURE", "TESTING"]
        return {k: getattr(self, k) for k in keys}
