"""Search Manager blueprint."""
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import select

from ..db import db
from ..models import Account, SearchConfiguration, SearchStatus
from ..services import search_service
from ..services.account_service import ValidationError
from ..services.filtering import CONDITION_KEYWORDS
from ..services.marketplace_url import SORT_OPTIONS

bp = Blueprint("searches", __name__, url_prefix="/searches")


@bp.route("/")
@login_required
def index():
    searches = (
        db.scalars(
            select(SearchConfiguration)
            .where(SearchConfiguration.deleted_at.is_(None))
            .order_by(SearchConfiguration.created_at.desc())
        )
        .all()
    )
    accounts = db.scalars(select(Account).where(Account.enabled == True).order_by(Account.display_name)).all()  # noqa: E712

    return render_template(
        "searches/index.html",
        searches=searches,
        accounts=accounts,
        conditions=CONDITION_KEYWORDS,
        sort_options=SORT_OPTIONS,
    )


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    accounts = db.scalars(select(Account).where(Account.enabled == True).order_by(Account.display_name)).all()  # noqa: E712

    if request.method == "POST":
        try:
            search = search_service.create(db, request.form.to_dict())
            db.commit()
            flash(f"Search '{search.name}' created and activated.", "success")
            return redirect(url_for("searches.index"))
        except ValidationError as exc:
            flash(f"Validation error: {exc}", "danger")
        except Exception as exc:
            db.rollback()
            flash(f"Failed to create search: {exc}", "danger")

    return render_template(
        "searches/form.html",
        search=None,
        accounts=accounts,
        conditions=CONDITION_KEYWORDS,
        sort_options=SORT_OPTIONS,
    )


@bp.route("/<int:search_id>/edit", methods=["GET", "POST"])
@login_required
def edit(search_id: int):
    search = db.get(SearchConfiguration, search_id)
    if not search or search.deleted_at is not None:
        flash("Search not found.", "warning")
        return redirect(url_for("searches.index"))

    accounts = db.scalars(select(Account).where(Account.enabled == True).order_by(Account.display_name)).all()  # noqa: E712

    if request.method == "POST":
        try:
            search_service.update(db, search, request.form.to_dict())
            db.commit()
            flash(f"Search '{search.name}' updated successfully.", "success")
            return redirect(url_for("searches.index"))
        except ValidationError as exc:
            flash(f"Validation error: {exc}", "danger")
        except Exception as exc:
            db.rollback()
            flash(f"Failed to update search: {exc}", "danger")

    return render_template(
        "searches/form.html",
        search=search,
        accounts=accounts,
        conditions=CONDITION_KEYWORDS,
        sort_options=SORT_OPTIONS,
    )


@bp.route("/<int:search_id>/pause", methods=["POST"])
@login_required
def pause(search_id: int):
    search = db.get(SearchConfiguration, search_id)
    if search:
        search_service.pause(search)
        db.commit()
        flash(f"Search '{search.name}' paused.", "info")
    return redirect(url_for("searches.index"))


@bp.route("/<int:search_id>/resume", methods=["POST"])
@login_required
def resume(search_id: int):
    search = db.get(SearchConfiguration, search_id)
    if search:
        search_service.resume(search)
        db.commit()
        flash(f"Search '{search.name}' resumed.", "success")
    return redirect(url_for("searches.index"))


@bp.route("/<int:search_id>/duplicate", methods=["POST"])
@login_required
def duplicate(search_id: int):
    search = db.get(SearchConfiguration, search_id)
    if search:
        copy = search_service.duplicate(db, search)
        db.commit()
        flash(f"Search duplicated as '{copy.name}' (paused).", "success")
    return redirect(url_for("searches.index"))


@bp.route("/<int:search_id>/delete", methods=["POST"])
@login_required
def delete(search_id: int):
    search = db.get(SearchConfiguration, search_id)
    if search:
        search_service.soft_delete(search)
        db.commit()
        flash("Search deleted. Historical listings are preserved.", "info")
    return redirect(url_for("searches.index"))


@bp.route("/<int:search_id>/run-now", methods=["POST"])
@login_required
def run_now(search_id: int):
    scheduler = current_app.extensions.get("scheduler")
    if scheduler:
        ok = scheduler.trigger_search_now(search_id)
        if ok:
            flash("Search execution triggered immediately in background.", "success")
    return redirect(url_for("searches.index"))


@bp.route("/seed-presets", methods=["POST"])
@login_required
def seed_presets():
    preset_configs = [
        {
            "name": "Damaged Cars Under $3,000",
            "search_terms": "damaged car",
            "vehicle_condition": "damaged",
            "min_price": 100,
            "max_price": 3000,
            "interval_minutes": 10,
            "account": "auto",
            "notify_telegram": True,
            "status": "active",
        },
        {
            "name": "Blown Engine & Non-Running",
            "search_terms": "blown engine",
            "vehicle_condition": "blown_engine",
            "min_price": 100,
            "max_price": 2500,
            "interval_minutes": 10,
            "account": "auto",
            "notify_telegram": True,
            "status": "active",
        },
        {
            "name": "Mechanic Special & Repairable",
            "search_terms": "mechanic special",
            "vehicle_condition": "repairable",
            "min_price": 100,
            "max_price": 3500,
            "interval_minutes": 10,
            "account": "auto",
            "notify_telegram": True,
            "status": "active",
        },
    ]

    count = 0
    for data in preset_configs:
        try:
            search_service.create(db, data)
            count += 1
        except Exception:
            pass

    db.commit()
    flash(f"Successfully loaded {count} default vehicle search presets!", "success")
    return redirect(url_for("searches.index"))

