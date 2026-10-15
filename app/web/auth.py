"""Authentication routes: login, logout, profile change."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import db
from ..extensions import login_manager
from ..models import User, utcnow

bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.get(User, int(user_id))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("overview.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = db.scalar(select(User).where(User.username == username))
        if user and check_password_hash(user.password_hash, password):
            user.last_login_at = utcnow()
            db.commit()
            login_user(user, remember=remember)
            flash("Signed in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page if next_page and next_page.startswith("/") else url_for("overview.index"))

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out successfully.", "info")
    return redirect(url_for("auth.login"))
