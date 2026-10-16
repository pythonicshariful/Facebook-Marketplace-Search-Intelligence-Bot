"""Overview dashboard blueprint."""
from __future__ import annotations

from datetime import datetime, time

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, select

from ..db import db
from ..models import (
    Account,
    ActivityLog,
    Listing,
    SearchConfiguration,
    SearchExecution,
    SearchStatus,
    SessionStatus,
    TmAgent,
    TmJob,
    TmJobStatus,
    utcnow,
)
from ..services import settings_store as st

bp = Blueprint("overview", __name__)


@bp.route("/")
@login_required
def index():
    now = utcnow()
    today_start = datetime.combine(now.date(), time.min)

    # 1. Accounts statistics
    total_accounts = db.scalar(select(func.count(Account.id))) or 0
    available_accounts = (
        db.scalar(
            select(func.count(Account.id)).where(
                Account.enabled == True,  # noqa: E712
                Account.session_status == SessionStatus.READY,
            )
        )
        or 0
    )
    attention_accounts = (
        db.scalar(
            select(func.count(Account.id)).where(
                Account.session_status.in_([SessionStatus.NEEDS_ATTENTION, SessionStatus.EXPIRED, SessionStatus.ERROR])
            )
        )
        or 0
    )

    # 2. Searches statistics
    total_searches = db.scalar(select(func.count(SearchConfiguration.id)).where(SearchConfiguration.deleted_at.is_(None))) or 0
    active_searches = (
        db.scalar(
            select(func.count(SearchConfiguration.id)).where(
                SearchConfiguration.status == SearchStatus.ACTIVE,
                SearchConfiguration.deleted_at.is_(None),
            )
        )
        or 0
    )
    paused_searches = (
        db.scalar(
            select(func.count(SearchConfiguration.id)).where(
                SearchConfiguration.status == SearchStatus.PAUSED,
                SearchConfiguration.deleted_at.is_(None),
            )
        )
        or 0
    )
    waiting_searches = (
        db.scalar(
            select(func.count(SearchConfiguration.id)).where(
                SearchConfiguration.status == SearchStatus.WAITING_ACCOUNT,
                SearchConfiguration.deleted_at.is_(None),
            )
        )
        or 0
    )
    failed_searches = (
        db.scalar(
            select(func.count(SearchConfiguration.id)).where(
                SearchConfiguration.status == SearchStatus.FAILED,
                SearchConfiguration.deleted_at.is_(None),
            )
        )
        or 0
    )

    # 3. Listings statistics
    total_listings = db.scalar(select(func.count(Listing.id))) or 0
    new_today = db.scalar(select(func.count(Listing.id)).where(Listing.first_seen_at >= today_start)) or 0

    # 4. Telegram status
    tg_enabled = st.get(db, "telegram_enabled")
    tg_configured = st.has_secret(db, "telegram_bot_token") and bool(st.get(db, "telegram_chat_id"))

    # 5. Recent executions
    recent_executions = (
        db.scalars(
            select(SearchExecution)
            .order_by(SearchExecution.started_at.desc())
            .limit(10)
        )
        .all()
    )

    # 6. Recent application errors
    recent_errors = (
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.level.in_(["ERROR", "WARNING"]))
            .order_by(ActivityLog.created_at.desc())
            .limit(8)
        )
        .all()
    )

    # 7. Active running searches right now
    running_searches = (
        db.scalars(
            select(SearchConfiguration)
            .where(SearchConfiguration.is_running == True, SearchConfiguration.deleted_at.is_(None))  # noqa: E712
        )
        .all()
    )

    # 8. Tampermonkey Agent status
    tm_agents = db.scalars(select(TmAgent).order_by(TmAgent.last_heartbeat_at.desc())).all()
    active_tm_agent = next(
        (a for a in tm_agents if a.last_heartbeat_at and (now - a.last_heartbeat_at).total_seconds() < 45),
        None,
    )
    pending_tm_jobs = db.scalar(select(func.count(TmJob.id)).where(TmJob.status == TmJobStatus.PENDING)) or 0
    tm_paused = st.get(db, "tm_agent_paused")

    return render_template(
        "overview/index.html",
        total_accounts=total_accounts,
        available_accounts=available_accounts,
        attention_accounts=attention_accounts,
        total_searches=total_searches,
        active_searches=active_searches,
        paused_searches=paused_searches,
        waiting_searches=waiting_searches,
        failed_searches=failed_searches,
        total_listings=total_listings,
        new_today=new_today,
        tg_enabled=tg_enabled,
        tg_configured=tg_configured,
        recent_executions=recent_executions,
        recent_errors=recent_errors,
        running_searches=running_searches,
        active_tm_agent=active_tm_agent,
        pending_tm_jobs=pending_tm_jobs,
        tm_paused=tm_paused,
    )
