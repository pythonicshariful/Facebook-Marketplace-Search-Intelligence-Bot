"""Activity log helper: writes to both the Python logger and the DB table
shown on the dashboard's Activity Logs page."""
from __future__ import annotations

import logging

from ..db import session_scope
from ..models import ActivityLog
from ..security import redact

log = logging.getLogger("fmbot.activity")


def log_event(level: str, category: str, message: str, *, account_id: int | None = None,
              search_id: int | None = None) -> None:
    level = level.upper()
    clean = redact(message)
    log.log(getattr(logging, level, logging.INFO), "[%s] %s", category, clean)
    try:
        with session_scope() as s:
            s.add(ActivityLog(level=level, category=category, message=clean[:4000],
                              account_id=account_id, search_id=search_id))
    except Exception:  # never let logging break a job
        log.exception("Failed to persist activity log entry")


def info(category: str, message: str, **kw) -> None:
    log_event("INFO", category, message, **kw)


def warning(category: str, message: str, **kw) -> None:
    log_event("WARNING", category, message, **kw)


def error(category: str, message: str, **kw) -> None:
    log_event("ERROR", category, message, **kw)
