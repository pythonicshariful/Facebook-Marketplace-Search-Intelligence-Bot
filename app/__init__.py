"""Flask Application Factory."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Flask, redirect, url_for
from werkzeug.security import generate_password_hash

from .config import Config
from .db import create_all, db, init_engine, session_scope
from .extensions import csrf, login_manager
from .logging_setup import setup_logging
from .models import User
from .security import init_secret_box, register_secret
from .services import settings_store as st
from .services.browser_service import BrowserManager
from .services.scheduler import SearchScheduler

log = logging.getLogger("fmbot.app")


def create_app(cfg: Optional[Config] = None, start_scheduler: bool = True) -> Flask:
    if cfg is None:
        cfg = Config()
    cfg.ensure_dirs()

    # 1. Setup logging and security box
    setup_logging(cfg.LOG_DIR, cfg.LOG_LEVEL)
    if cfg.FERNET_KEY:
        init_secret_box(cfg.FERNET_KEY)

    # 2. Database init
    init_engine(cfg.DATABASE_URL)
    create_all()

    # 3. Create Flask instance
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(cfg.to_flask())
    app.config["APP_CONFIG"] = cfg

    # 4. Init extensions
    login_manager.init_app(app)
    csrf.init_app(app)

    # 5. Register blueprints
    from .web import accounts, api, auth, listings, logs, monitoring, overview, searches, settings, telegram, tm_api

    app.register_blueprint(auth.bp)
    app.register_blueprint(overview.bp)
    app.register_blueprint(accounts.bp)
    app.register_blueprint(searches.bp)
    app.register_blueprint(monitoring.bp)
    app.register_blueprint(listings.bp)
    app.register_blueprint(telegram.bp)
    app.register_blueprint(logs.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(tm_api.bp)

    # 6. Teardown scoped session
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.remove()

    # 7. Context processors and template filters
    @app.template_filter("format_dt")
    def format_dt(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
        if not dt:
            return "—"
        local = dt.replace(tzinfo=timezone.utc).astimezone()
        return local.strftime(fmt)

    @app.template_filter("format_price")
    def format_price(cents: Optional[int]) -> str:
        if cents is None:
            return "Unknown"
        return f"${cents / 100:,.0f}"

    # 8. Bootstrap initial admin user & Telegram env values
    with session_scope() as s:
        if not s.query(User).first():
            # Create default admin user (admin / admin123)
            # Operator will be prompted to change it or use create_user.py
            default_admin = User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                role="admin",
            )
            s.add(default_admin)
            log.info("Default user 'admin' created with password 'admin123'. Change via scripts/create_user.py.")

        # If TELEGRAM_BOT_TOKEN / CHAT_ID was passed in .env and not in DB yet, import them
        if cfg.TELEGRAM_BOT_TOKEN and not st.has_secret(s, "telegram_bot_token"):
            st.set_secret(s, "telegram_bot_token", cfg.TELEGRAM_BOT_TOKEN)
            log.info("Imported Telegram Bot Token from environment.")
        if cfg.TELEGRAM_CHAT_ID and not st.get(s, "telegram_chat_id"):
            st.set_value(s, "telegram_chat_id", cfg.TELEGRAM_CHAT_ID)
            st.set_value(s, "telegram_enabled", True)
            log.info("Imported Telegram Chat ID from environment and enabled notifications.")

    # 9. Initialise BrowserManager and Scheduler
    browser_manager = BrowserManager(
        locks_dir=cfg.LOCKS_DIR,
        chrome_binary=cfg.CHROME_BINARY,
        chromedriver_path=cfg.CHROMEDRIVER_PATH,
        version_main=getattr(cfg, "CHROME_VERSION_MAIN", 0) or None,
    )
    scheduler = SearchScheduler(cfg, browser_manager)
    app.extensions["browser_manager"] = browser_manager
    app.extensions["scheduler"] = scheduler

    if start_scheduler and cfg.SCHEDULER_ENABLED and not cfg.TESTING:
        scheduler.start()

    return app
