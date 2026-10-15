"""Activity logs blueprint."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, request, send_file
from flask_login import login_required
from sqlalchemy import select

from ..db import db
from ..models import ActivityLog

bp = Blueprint("logs", __name__, url_prefix="/logs")


@bp.route("/")
@login_required
def index():
    level = request.args.get("level", "").upper()
    category = request.args.get("category", "").lower()
    limit = min(200, max(20, request.args.get("limit", 100, type=int)))

    stmt = select(ActivityLog)
    if level:
        stmt = stmt.where(ActivityLog.level == level)
    if category:
        stmt = stmt.where(ActivityLog.category == category)

    stmt = stmt.order_by(ActivityLog.created_at.desc()).limit(limit)
    logs = db.scalars(stmt).all()

    return render_template(
        "logs/index.html",
        logs=logs,
        current_level=level,
        current_category=category,
        limit=limit,
    )


@bp.route("/download/<name>")
@login_required
def download_file(name: str):
    """Download rotating log file from logs/ directory."""
    log_dir = Path(current_app.config["APP_CONFIG"].LOG_DIR)
    target = (log_dir / name).resolve()

    # Prevent directory traversal
    if not target.is_relative_to(log_dir.resolve()) or not target.exists():
        return "File not found", 404

    return send_file(target, as_attachment=True)
