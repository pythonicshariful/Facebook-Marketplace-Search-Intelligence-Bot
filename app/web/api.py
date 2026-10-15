"""API blueprint for dynamic asynchronous dashboard polling."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import login_required
from sqlalchemy import select

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

    return jsonify({
        "scheduler_active": scheduler._is_active if scheduler else False,
        "browsers": browser_snapshot,
        "accounts": account_data,
        "running_search_ids": running_searches,
    })
