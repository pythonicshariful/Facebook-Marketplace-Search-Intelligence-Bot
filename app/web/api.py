"""API blueprint for dynamic asynchronous dashboard polling."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import login_required
from sqlalchemy import func, select

from ..db import db
from ..models import Account, SearchConfiguration, SearchExecution

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/status")
@login_required
def status():
    scheduler = current_app.extensions.get("scheduler")
    browser_snapshot = scheduler.browser_manager.snapshot() if scheduler else []

    accounts = db.scalars(select(Account).order_by(Account.id)).all()
    account_data = [
        {
            "id": a.id,
            "display_name": a.display_name,
            "session_status": a.session_status,
            "status_label": a.status_label,
            "status_message": a.status_message,
            "enabled": a.enabled,
            "is_busy": scheduler.browser_manager.is_busy(a.id) if scheduler else False,
            "is_open": scheduler.browser_manager.is_open(a.id) if scheduler else False,
        }
        for a in accounts
    ]

    running_searches = db.scalars(
        select(SearchConfiguration.id).where(
            SearchConfiguration.is_running == True,  # noqa: E712
            SearchConfiguration.deleted_at.is_(None),
        )
    ).all()

    from ..models import TmAgent, TmJob, TmJobStatus, utcnow

    now = utcnow()
    tm_agents = db.scalars(select(TmAgent)).all()
    active_tm_agent = next((a for a in tm_agents if a.last_heartbeat_at and (now - a.last_heartbeat_at).total_seconds() < 45), None)
    pending_tm_jobs = db.scalar(select(func.count(TmJob.id)).where(TmJob.status == TmJobStatus.PENDING)) or 0

    return jsonify({
        "scheduler_active": scheduler._is_active if scheduler else False,
        "browsers": browser_snapshot,
        "accounts": account_data,
        "running_search_ids": running_searches,
        "tm_agent": {
            "online": bool(active_tm_agent),
            "agent_id": active_tm_agent.agent_id if active_tm_agent else None,
            "status": active_tm_agent.status if active_tm_agent else "offline",
            "fb_user": active_tm_agent.fb_user if active_tm_agent else None,
            "pending_jobs": pending_tm_jobs,
        },
    })
