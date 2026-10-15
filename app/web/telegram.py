"""Telegram settings & test notification blueprint."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..db import db
from ..services import activity
from ..services import settings_store as st
from ..services import telegram_service
from ..services.telegram_service import TelegramError

bp = Blueprint("telegram", __name__, url_prefix="/telegram")


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "save":
            bot_token = request.form.get("telegram_bot_token", "").strip()
            chat_id = request.form.get("telegram_chat_id", "").strip()
            enabled = bool(request.form.get("telegram_enabled"))
            disable_preview = bool(request.form.get("telegram_disable_preview"))
            silent = bool(request.form.get("telegram_silent"))

            try:
                # Update token if provided (leave unchanged if blank)
                if bot_token:
                    st.set_secret(db, "telegram_bot_token", bot_token)
                st.set_value(db, "telegram_chat_id", chat_id)
                st.set_value(db, "telegram_enabled", enabled)
                st.set_value(db, "telegram_disable_preview", disable_preview)
                st.set_value(db, "telegram_silent", silent)
                db.commit()
                flash("Telegram settings saved successfully.", "success")
                activity.info("settings", "Telegram settings updated.")
            except Exception as exc:
                db.rollback()
                flash(f"Error saving settings: {exc}", "danger")

        elif action == "test":
            try:
                msg_id = telegram_service.send_test(db)
                flash(f"Test notification delivered successfully! (Message ID: {msg_id})", "success")
                activity.info("telegram", f"Test notification sent successfully (ID: {msg_id})")
            except TelegramError as exc:
                flash(f"Telegram test failed: {exc}", "danger")
                activity.warning("telegram", f"Test notification failed: {exc}")
            except Exception as exc:
                flash(f"Unexpected error: {exc}", "danger")

        return redirect(url_for("telegram.index"))

    token_configured = st.has_secret(db, "telegram_bot_token")
    chat_id = st.get(db, "telegram_chat_id")
    enabled = st.get(db, "telegram_enabled")
    disable_preview = st.get(db, "telegram_disable_preview")
    silent = st.get(db, "telegram_silent")

    return render_template(
        "telegram/index.html",
        token_configured=token_configured,
        chat_id=chat_id,
        enabled=enabled,
        disable_preview=disable_preview,
        silent=silent,
    )
