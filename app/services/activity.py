from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import ActivityLog
from ..security import redact

log = logging.getLogger("fmbot.activity")


def log_event(level: str, category: str, message: str, *, account_id: int | None = None,
              search_id: int | None = None, session: Optional[Session] = None) -> None:
    level = level.upper()
    clean = redact(message)
    log.log(getattr(logging, level, logging.INFO), "[%s] %s", category, clean)
    try:
        entry = ActivityLog(level=level, category=category, message=clean[:4000],
                            account_id=account_id, search_id=search_id)
        if session is not None:
            # Participate directly in the caller's active transaction (no second connection / deadlock)
            session.add(entry)
            return

        for attempt in range(4):
            try:
                with session_scope() as s:
                    s.add(entry)
                break
            except Exception as exc:
                if "locked" in str(exc).lower() and attempt < 3:
                    time.sleep(0.15 * (attempt + 1))
                    continue
                raise
    except Exception:  # never let logging break a job
        log.exception("Failed to persist activity log entry")


def info(category: str, message: str, **kw) -> None:
    log_event("INFO", category, message, **kw)


def warning(category: str, message: str, **kw) -> None:
    log_event("WARNING", category, message, **kw)


def error(category: str, message: str, **kw) -> None:
    log_event("ERROR", category, message, **kw)
