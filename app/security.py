"""Secret encryption and sensitive-value redaction."""
from __future__ import annotations

import logging
import re

from cryptography.fernet import Fernet, InvalidToken

# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------
_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Telegram bot tokens: 123456789:AA... (also inside api.telegram.org/bot<token>/)
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), "[REDACTED_BOT_TOKEN]"),
    (re.compile(r"(api\.telegram\.org/bot)[^/\s]+"), r"\1[REDACTED]"),
    # Facebook session cookies & generic cookie/auth headers
    (re.compile(r"\b(c_user|xs|fr|datr|sb|presence|spin)=[^;\s,]+", re.I), r"\1=[REDACTED]"),
    (re.compile(r"(cookie|set-cookie|authorization)(\s*[:=]\s*)[^\n]+", re.I), r"\1\2[REDACTED]"),
    (re.compile(r"(password|passwd|pass|token|secret|api_key)(\"?\s*[:=]\s*\"?)[^\s\"',;&]+", re.I),
     r"\1\2[REDACTED]"),
]

_extra_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret value that must never appear in logs."""
    if value and len(value) >= 6:
        _extra_secrets.add(value)


def redact(text: object) -> str:
    s = str(text)
    for secret in list(_extra_secrets):
        if secret in s:
            s = s.replace(secret, "[REDACTED]")
    for pattern, repl in _REDACTION_PATTERNS:
        s = pattern.sub(repl, s)
    return s


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        record.msg = redact(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


# --------------------------------------------------------------------------
# Encryption
# --------------------------------------------------------------------------
class SecretBox:
    """Thin wrapper around Fernet. Keys come from the environment only."""

    def __init__(self, key: str | None):
        self._fernet = None
        if key:
            try:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
            except (ValueError, TypeError) as exc:
                raise ValueError("FMBOT_FERNET_KEY is not a valid Fernet key") from exc

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Encryption key not configured (FMBOT_FERNET_KEY)")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        if not self._fernet or not token:
            return None
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            return None


_box: SecretBox | None = None


def init_secret_box(key: str | None) -> SecretBox:
    global _box
    _box = SecretBox(key)
    return _box


def secret_box() -> SecretBox:
    if _box is None:
        raise RuntimeError("Secret box not initialised")
    return _box
