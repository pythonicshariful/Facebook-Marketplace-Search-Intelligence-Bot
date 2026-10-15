"""Account Manager blueprint."""
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    Response,
    url_for,
)
from flask_login import login_required
from sqlalchemy import select

from ..db import db
from ..models import Account, SessionStatus
from ..services import account_service
from ..services.account_service import ValidationError

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
@login_required
def index():
    accounts = db.scalars(select(Account).order_by(Account.id)).all()
    scheduler = current_app.extensions.get("scheduler")
    browser_snapshot = scheduler.browser_manager.snapshot() if scheduler else []
    open_account_ids = {item["account_id"] for item in browser_snapshot}

    return render_template(
        "accounts/index.html",
        accounts=accounts,
        open_account_ids=open_account_ids,
        browser_snapshot=browser_snapshot,
    )


@bp.route("/add", methods=["POST"])
@login_required
def add():
    display_name = request.form.get("display_name", "").strip()
    daily_run_limit = request.form.get("daily_run_limit", 0)
    notes = request.form.get("notes", "")

    try:
        acc = account_service.create_account(
            db,
            current_app.config["APP_CONFIG"],
            display_name=display_name,
            daily_run_limit=daily_run_limit,
            notes=notes,
            enabled=True,
        )
        db.commit()
        flash(f"Account '{acc.display_name}' created with profile path: {acc.profile_dir}", "success")
    except ValidationError as exc:
        flash(f"Could not create account: {exc}", "danger")
    except Exception as exc:
        db.rollback()
        flash(f"Failed to create account: {exc}", "danger")

    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/edit", methods=["POST"])
@login_required
def edit(account_id: int):
    acc = db.get(Account, account_id)
    if not acc:
        flash("Account not found.", "warning")
        return redirect(url_for("accounts.index"))

    display_name = request.form.get("display_name", "").strip()
    daily_run_limit = request.form.get("daily_run_limit", 0)
    notes = request.form.get("notes", "")
    enabled = bool(request.form.get("enabled"))

    try:
        account_service.update_account(
            db,
            acc,
            display_name=display_name,
            daily_run_limit=daily_run_limit,
            notes=notes,
            enabled=enabled,
        )
        db.commit()
        flash(f"Account '{acc.display_name}' updated successfully.", "success")
    except ValidationError as exc:
        flash(f"Could not update account: {exc}", "danger")
    except Exception as exc:
        db.rollback()
        flash(f"Error updating account: {exc}", "danger")

    return redirect(url_for("accounts.index"))


@bp.route("/save-all", methods=["POST"])
@login_required
def save_all():
    """Save Accounts batch validation and persistence."""
    rows = []
    # Collect form entries: display_name_<id>, enabled_<id>, daily_run_limit_<id>, notes_<id>
    accounts = db.scalars(select(Account)).all()
    for acc in accounts:
        name_key = f"display_name_{acc.id}"
        if name_key in request.form:
            rows.append({
                "id": acc.id,
                "display_name": request.form.get(name_key, "").strip(),
                "daily_run_limit": request.form.get(f"daily_run_limit_{acc.id}", 0),
                "notes": request.form.get(f"notes_{acc.id}", ""),
                "enabled": bool(request.form.get(f"enabled_{acc.id}")),
            })

    if not rows:
        flash("No account changes to save.", "info")
        return redirect(url_for("accounts.index"))

    try:
        count = account_service.save_accounts(db, current_app.config["APP_CONFIG"], rows)
        db.commit()
        flash(f"Successfully validated and saved {count} account(s). Configuration persisted to database.", "success")
    except ValidationError as exc:
        db.rollback()
        flash(f"Save Accounts validation failed: {exc}", "danger")
    except Exception as exc:
        db.rollback()
        flash(f"Failed to save accounts: {exc}", "danger")

    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/toggle", methods=["POST"])
@login_required
def toggle(account_id: int):
    acc = db.get(Account, account_id)
    if not acc:
        flash("Account not found.", "warning")
        return redirect(url_for("accounts.index"))

    account_service.set_enabled(db, acc, not acc.enabled)
    db.commit()
    status = "enabled" if acc.enabled else "disabled"
    flash(f"Account '{acc.display_name}' is now {status}.", "info")
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
def delete(account_id: int):
    acc = db.get(Account, account_id)
    if not acc:
        flash("Account not found.", "warning")
        return redirect(url_for("accounts.index"))

    delete_files = bool(request.form.get("delete_files"))
    name = acc.display_name
    account_service.delete_account(db, current_app.config["APP_CONFIG"], acc, delete_profile=delete_files)
    db.commit()
    flash(f"Account '{name}' has been removed.", "success")
    return redirect(url_for("accounts.index"))


# --- Manual Login / Session actions ---

@bp.route("/<int:account_id>/open-login", methods=["POST"])
@login_required
def open_login(account_id: int):
    scheduler = current_app.extensions.get("scheduler")
    if scheduler:
        scheduler.trigger_login_flow(account_id)
        flash("Launching Chrome window for manual login. Please log in manually inside the browser.", "info")
    else:
        flash("Scheduler is not active.", "danger")
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/confirm-login", methods=["POST"])
@login_required
def confirm_login(account_id: int):
    scheduler = current_app.extensions.get("scheduler")
    if scheduler:
        scheduler.trigger_confirm_login(account_id)
        flash("Verifying login state in the browser window...", "info")
    else:
        flash("Scheduler is not active.", "danger")
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/verify", methods=["POST"])
@login_required
def verify(account_id: int):
    scheduler = current_app.extensions.get("scheduler")
    if scheduler:
        scheduler.trigger_verify_session(account_id)
        flash("Verifying Facebook Marketplace access for account...", "info")
    else:
        flash("Scheduler is not active.", "danger")
    return redirect(url_for("accounts.index"))


@bp.route("/<int:account_id>/close-browser", methods=["POST"])
@login_required
def close_browser(account_id: int):
    scheduler = current_app.extensions.get("scheduler")
    if scheduler:
        scheduler.trigger_close_browser(account_id)
        flash("Closing browser window and releasing profile lock...", "info")
    return redirect(url_for("accounts.index"))


# --- Exports ---

@bp.route("/export/json")
@login_required
def export_json():
    data = account_service.export_json_bytes(db)
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=accounts_metadata.json"},
    )


@bp.route("/export/pkl")
@login_required
def export_pkl():
    """Optional non-sensitive pickle export (export only; pickle is never imported)."""
    data = account_service.export_pickle_bytes(db)
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=accounts_metadata.pkl"},
    )
