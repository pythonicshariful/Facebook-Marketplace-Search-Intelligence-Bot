"""SQLAlchemy ORM models.

All timestamps are stored as *naive UTC* datetimes. The UI converts them to
the viewer's local time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin
from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, CheckConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Status vocabularies
# --------------------------------------------------------------------------
class SessionStatus:
    NEW = "new"                          # profile created, never logged in
    WAITING_LOGIN = "waiting_login"      # browser open, operator logging in
    READY = "ready"                      # verified logged-in session
    UNVERIFIED = "unverified"            # state unknown (e.g. after restart mid-login)
    EXPIRED = "expired"                  # login required again
    NEEDS_ATTENTION = "needs_attention"  # checkpoint / captcha / restriction
    ERROR = "error"                      # technical error (browser failed etc.)

    LABELS = {
        NEW: "Not logged in",
        WAITING_LOGIN: "Waiting for Manual Login",
        READY: "Session Ready",
        UNVERIFIED: "Unverified",
        EXPIRED: "Login Required",
        NEEDS_ATTENTION: "Needs Attention",
        ERROR: "Error",
    }


class SearchStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    WAITING_ACCOUNT = "waiting_account"
    FAILED = "failed"

    LABELS = {ACTIVE: "Active", PAUSED: "Paused", WAITING_ACCOUNT: "Waiting for account",
              FAILED: "Failed"}


class ExecStatus:
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"            # technical/recoverable failure
    BLOCKED = "blocked"          # login wall / checkpoint / restriction
    WAITING_ACCOUNT = "waiting_account"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


class NotifyStatus:
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"            # will be retried (bounded)
    GAVE_UP = "gave_up"          # retries exhausted
    SKIPPED = "skipped"


# --------------------------------------------------------------------------
class User(UserMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="admin", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (CheckConstraint("role in ('admin','viewer')", name="ck_user_role"),)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    profile_dir: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_status: Mapped[str] = mapped_column(String(32), default=SessionStatus.NEW, nullable=False, index=True)
    status_message: Mapped[Optional[str]] = mapped_column(Text)
    daily_run_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = unlimited
    notes: Mapped[Optional[str]] = mapped_column(Text)

    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    login_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    login_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    searches: Mapped[list["SearchConfiguration"]] = relationship(
        back_populates="account", foreign_keys="SearchConfiguration.account_id")

    __table_args__ = (CheckConstraint("daily_run_limit >= 0", name="ck_account_limit"),)

    @property
    def status_label(self) -> str:
        return SessionStatus.LABELS.get(self.session_status, self.session_status)

    @property
    def internal_id(self) -> str:
        return f"account_{self.id:03d}"


class SearchConfiguration(Base):
    __tablename__ = "search_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    search_terms: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    make: Mapped[Optional[str]] = mapped_column(String(60))
    model: Mapped[Optional[str]] = mapped_column(String(60))
    location: Mapped[Optional[str]] = mapped_column(String(120))        # human label / ZIP
    location_slug: Mapped[Optional[str]] = mapped_column(String(120))   # Marketplace URL segment
    radius_miles: Mapped[Optional[int]] = mapped_column(Integer)
    min_price: Mapped[Optional[int]] = mapped_column(Integer)           # whole dollars
    max_price: Mapped[Optional[int]] = mapped_column(Integer)
    vehicle_condition: Mapped[str] = mapped_column(String(32), default="any", nullable=False)
    include_keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exclude_keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sort_by: Mapped[str] = mapped_column(String(32), default="newest", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    fetch_details: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    account_mode: Mapped[str] = mapped_column(String(16), default="specific", nullable=False)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default=SearchStatus.ACTIVE, nullable=False, index=True)
    status_message: Mapped[Optional[str]] = mapped_column(Text)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    last_selection_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)  # soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    account: Mapped[Optional[Account]] = relationship(back_populates="searches", foreign_keys=[account_id])
    last_account: Mapped[Optional[Account]] = relationship(foreign_keys=[last_account_id])

    __table_args__ = (
        CheckConstraint("account_mode in ('specific','auto')", name="ck_search_account_mode"),
        CheckConstraint("interval_minutes >= 1", name="ck_search_interval"),
        Index("ix_search_due", "status", "next_run_at"),
    )

    @property
    def status_label(self) -> str:
        return SearchStatus.LABELS.get(self.status, self.status)


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)  # fb:<id> | fp:<hash>
    key_type: Mapped[str] = mapped_column(String(16), nullable=False)  # fb_id | fingerprint
    fb_item_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    price_text: Mapped[Optional[str]] = mapped_column(String(64))
    price_cents: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(160))
    condition: Mapped[Optional[str]] = mapped_column(String(120))
    mileage: Mapped[Optional[str]] = mapped_column(String(60))
    seller_name: Mapped[Optional[str]] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000))
    posted_text: Mapped[Optional[str]] = mapped_column(String(120))  # as displayed by FB, if any
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    first_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))

    search_links: Mapped[list["SearchListing"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    first_account: Mapped[Optional[Account]] = relationship()


class SearchListing(Base):
    """Association between a search and a listing it has seen."""
    __tablename__ = "search_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_configurations.id", ondelete="CASCADE"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    match_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="search_links")
    search: Mapped[SearchConfiguration] = relationship()
    account: Mapped[Optional[Account]] = relationship()

    __table_args__ = (UniqueConstraint("search_id", "listing_id", name="uq_search_listing"),)


class SearchExecution(Base):
    __tablename__ = "search_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_configurations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=ExecStatus.RUNNING, nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    page_state: Mapped[Optional[str]] = mapped_column(String(32))
    url: Mapped[Optional[str]] = mapped_column(String(800))
    found_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selection_reason: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    search: Mapped[SearchConfiguration] = relationship()
    account: Mapped[Optional[Account]] = relationship()

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique dedup key enforces "notify once" at the DB level, even under
    # concurrent workers. NULL for test messages (NULLs never collide).
    dedup_key: Mapped[Optional[str]] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default="new", nullable=False)  # new | price_drop | test
    listing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    search_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_configurations.id", ondelete="SET NULL"), index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    execution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_executions.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(16), default="telegram", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=NotifyStatus.PENDING, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    external_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    listing: Mapped[Optional[Listing]] = relationship()
    search: Mapped[Optional[SearchConfiguration]] = relationship()
    account: Mapped[Optional[Account]] = relationship()


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # value is Fernet-encrypted
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), default="INFO", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(24), default="system", nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    search_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_configurations.id", ondelete="SET NULL"))


# --------------------------------------------------------------------------
# Tampermonkey Agent Models
# --------------------------------------------------------------------------
class TmJobStatus:
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"


class TmJob(Base):
    __tablename__ = "tm_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_configurations.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_executions.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=TmJobStatus.PENDING, nullable=False, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded search parameters
    progress_step: Mapped[Optional[str]] = mapped_column(String(120))
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    search: Mapped[SearchConfiguration] = relationship()
    execution: Mapped[Optional[SearchExecution]] = relationship()


class TmAgent(Base):
    __tablename__ = "tm_agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Tampermonkey Agent", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)  # idle, busy, paused
    fb_user: Mapped[Optional[str]] = mapped_column(String(120))
    current_url: Mapped[Optional[str]] = mapped_column(String(500))
    current_job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tm_jobs.id", ondelete="SET NULL"))
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
