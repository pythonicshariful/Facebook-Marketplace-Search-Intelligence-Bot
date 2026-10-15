"""Database engine/session management (SQLAlchemy 2.x).

* Flask request handlers use ``db`` (a thread-local scoped session that is
  removed at the end of each request).
* Background workers use ``session_scope()`` which yields an independent
  session and commits/rolls back automatically.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(expire_on_commit=False, future=True)
db = scoped_session(SessionLocal)
_engine: Engine | None = None


def init_engine(url: str, echo: bool = False) -> Engine:
    global _engine
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, echo=echo, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    db.remove()
    SessionLocal.configure(bind=engine)
    if _engine is not None and _engine is not engine:
        _engine.dispose()
    _engine = engine
    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not initialised")
    return _engine


def create_all() -> None:
    from . import models  # noqa: F401  (register models)
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
