"""Application Settings blueprint."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required

from ..db import db
from ..services import activity
from ..services import backup_service
from ..services import settings_store as st

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    cfg = current_app.config["APP_CONFIG"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save":
            try:
                for key in st.DEFAULTS:
                    if key in st.SECRET_KEYS:
                        continue
                    if key.startswith("telegram_"):
                        continue  # Managed in telegram tab
                    
                    if key in request.form or key in ["auto_select_allowed", "headless", "keep_browsers_open", "renotify_price_drop", "notify_unknown_price"]:
                        val = request.form.get(key)
                        # Checkboxes need boolean conversion if missing from form
                        if isinstance(st.DEFAULTS[key], bool):
                            val = bool(val)
                        if val is not None:
                            st.set_value(db, key, val)

                db.commit()
                flash("Application settings updated successfully.", "success")
                activity.info("settings", "Application settings modified by operator.")
            except Exception as exc:
                db.rollback()
                flash(f"Failed to save settings: {exc}", "danger")

        elif action == "backup_now":
            try:
                archive = backup_service.create_backup(cfg)
                flash(f"Backup created successfully: {archive.name}", "success")
            except Exception as exc:
                flash(f"Backup failed: {exc}", "danger")

        return redirect(url_for("settings.index"))

    settings = st.get_all(db)
    backups = backup_service.list_backups(cfg)

    return render_template(
        "settings/index.html",
        settings=settings,
        backups=backups,
    )


@bp.route("/backup/download/<name>")
@login_required
def download_backup(name: str):
    cfg = current_app.config["APP_CONFIG"]
    target = (cfg.BACKUP_DIR / name).resolve()
    if not target.is_relative_to(cfg.BACKUP_DIR.resolve()) or not target.exists():
        return "Backup not found", 404
    return send_file(target, as_attachment=True)
