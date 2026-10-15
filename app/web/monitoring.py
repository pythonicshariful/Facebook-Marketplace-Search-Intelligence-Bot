"""Live Monitoring blueprint."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template
from flask_login import login_required
from sqlalchemy import select

from ..db import db
from ..models import Account, SearchConfiguration, SearchExecution

bp = Blueprint("monitoring", __name__, url_prefix="/monitoring")


@bp.route("/")
@login_required
def index():
    scheduler = current_app.extensions.get("scheduler")
    browser_snapshot = scheduler.browser_manager.snapshot() if scheduler else []

    active_executions = (
        db.scalars(
            select(SearchExecution)
            .where(SearchExecution.status == "running")
            .order_by(SearchExecution.started_at.desc())
        )
        .all()
    )

    recent_executions = (
        db.scalars(
            select(SearchExecution)
            .order_by(SearchExecution.started_at.desc())
            .limit(30)
        )
        .all()
    )

    running_searches = (
        db.scalars(
            select(SearchConfiguration)
            .where(SearchConfiguration.is_running == True, SearchConfiguration.deleted_at.is_(None))  # noqa: E712
        )
        .all()
    )

    return render_template(
        "monitoring/index.html",
        browser_snapshot=browser_snapshot,
        active_executions=active_executions,
        recent_executions=recent_executions,
        running_searches=running_searches,
    )
