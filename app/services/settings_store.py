"""Typed application settings stored in the ``application_settings`` table.

Secrets (``SECRET_KEYS``) are Fernet-encrypted at rest and are never returned
to templates – only a boolean "configured" flag is exposed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import ApplicationSetting
from ..security import register_secret, secret_box

DEFAULTS: dict[str, Any] = {
    # Scheduling
    "min_interval_minutes": 10,
    "default_interval_minutes": 10,
    "max_concurrent_jobs": 2,
    "max_retries_recoverable": 2,
    "retry_backoff_seconds": 120,
    "max_consecutive_failures": 5,
    "waiting_recheck_seconds": 120,
    # Browser
    "page_load_timeout": 45,
    "element_wait_timeout": 20,
    "login_timeout_minutes": 0,         # 0 = wait indefinitely
    "max_scroll_rounds": 2,
    "scroll_pause_seconds": 2.5,
    "max_detail_pages_per_run": 5,
    "headless": False,
    "keep_browsers_open": True,
    # Account selection
    "auto_select_allowed": True,
    # Dedup / notifications
    "dedup_scope": "global",            # global | per_search
    "renotify_price_drop": False,
    "notify_unknown_price": True,
    "notification_max_attempts": 4,
    # Telegram
    "telegram_enabled": False,
    "telegram_chat_id": "",
    "telegram_disable_preview": False,
    "telegram_silent": False,
    # Maintenance
    "backup_retention": 14,
    # Tampermonkey Browser Agent
    "tm_api_token": "fb-marketplace-tm-token-secret",
    "tm_agent_paused": False,
    "scraper_mode": "tampermonkey",     # tampermonkey | selenium
}

SECRET_KEYS = {"telegram_bot_token"}

_CHOICES = {
    "dedup_scope": {"global", "per_search"},
    "scraper_mode": {"tampermonkey", "selenium"},
}
_BOUNDS = {
    "min_interval_minutes": (1, 1440),
    "default_interval_minutes": (1, 1440),
    "max_concurrent_jobs": (1, 8),
    "max_retries_recoverable": (0, 5),
    "retry_backoff_seconds": (10, 3600),
    "max_consecutive_failures": (1, 50),
    "waiting_recheck_seconds": (30, 3600),
    "page_load_timeout": (10, 180),
    "element_wait_timeout": (5, 120),
    "login_timeout_minutes": (0, 1440),
    "max_scroll_rounds": (0, 10),
    "scroll_pause_seconds": (0.5, 15),
    "max_detail_pages_per_run": (0, 25),
    "notification_max_attempts": (1, 10),
    "backup_retention": (1, 365),
}


def _cast(key: str, raw: Any) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(float(raw))
    if isinstance(default, float):
        return float(raw)
    return "" if raw is None else str(raw)


def get(session: Session, key: str) -> Any:
    if key in SECRET_KEYS:
        raise KeyError("Use get_secret() for secret settings")
    row = session.get(ApplicationSetting, key)
    if row is None or row.value is None:
        return DEFAULTS[key]
    try:
        return _cast(key, row.value)
    except (TypeError, ValueError):
        return DEFAULTS[key]


def get_all(session: Session) -> dict[str, Any]:
    return {k: get(session, k) for k in DEFAULTS}


def validate(key: str, raw: Any) -> Any:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key}")
    try:
        value = _cast(key, raw)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid value for {key}")
    if key in _BOUNDS:
        lo, hi = _BOUNDS[key]
        if not (lo <= value <= hi):
            raise ValueError(f"{key} must be between {lo} and {hi}")
    if key in _CHOICES and value not in _CHOICES[key]:
        raise ValueError(f"{key} must be one of {sorted(_CHOICES[key])}")
    if key == "telegram_chat_id" and value:
        v = value.strip()
        if not (v.lstrip("-").isdigit() or v.startswith("@")):
            raise ValueError("Telegram chat ID must be numeric (e.g. 123456789 / -100...) or @channelname")
        value = v
    return value


def set_value(session: Session, key: str, raw: Any) -> Any:
    value = validate(key, raw)
    row = session.get(ApplicationSetting, key)
    if row is None:
        row = ApplicationSetting(key=key)
        session.add(row)
    row.value = str(value)
    row.is_secret = False
    return value


def set_secret(session: Session, key: str, plaintext: str | None) -> None:
    if key not in SECRET_KEYS:
        raise KeyError(key)
    row = session.get(ApplicationSetting, key)
    if not plaintext:
        if row is not None:
            session.delete(row)
        return
    if row is None:
        row = ApplicationSetting(key=key)
        session.add(row)
    row.value = secret_box().encrypt(plaintext.strip())
    row.is_secret = True
    register_secret(plaintext.strip())


def get_secret(session: Session, key: str) -> str | None:
    row = session.get(ApplicationSetting, key)
    if row is None or not row.value:
        return None
    value = secret_box().decrypt(row.value)
    if value:
        register_secret(value)
    return value


def has_secret(session: Session, key: str) -> bool:
    return get_secret(session, key) is not None
