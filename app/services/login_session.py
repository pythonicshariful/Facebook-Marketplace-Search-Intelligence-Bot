"""Manual-login workflow and session verification.

* ``start_login``   – launch the account's profile in a VISIBLE Chrome window,
  open facebook.com and wait. Nothing is typed; the operator logs in and
  completes any legitimate security verification themselves.
* ``confirm_login`` – operator clicked "Confirm Login / Continue"; check the
  same window. On failure the browser is left open for troubleshooting.
* ``verify_session``– check an existing profile's Marketplace access.
* ``check_timeouts``– flag overdue logins (browser is NOT closed).

All methods are executed in background worker threads.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from . import activity
from . import settings_store as st
from .account_service import resolve_profile_dir
from .browser_service import (FACEBOOK_HOME, MARKETPLACE_HOME, BrowserManager, BrowserOptions,
                              navigate_and_classify, _has_login_cookie)
from .page_state import NEEDS_ATTENTION, SUCCESS, PageState, DESCRIPTIONS
from .profile_lock import ProfileBusyError
from ..config import Config
from ..db import session_scope
from ..models import Account, SessionStatus, utcnow

log = logging.getLogger("fmbot.login")


def browser_options(settings: dict) -> BrowserOptions:
    return BrowserOptions(headless=settings["headless"], page_load_timeout=settings["page_load_timeout"],
                          element_wait_timeout=settings["element_wait_timeout"],
                          max_scroll_rounds=settings["max_scroll_rounds"],
                          scroll_pause_seconds=settings["scroll_pause_seconds"])


class LoginService:
    def __init__(self, manager: BrowserManager, cfg: Config):
        self.manager = manager
        self.cfg = cfg

    def _set(self, account_id: int, status: str | None = None, message: str | None = None,
             error: str | None = None, success: bool = False, **fields) -> None:
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if not acc:
                return
            if status:
                acc.session_status = status
            if message is not None:
                acc.status_message = message
            if error:
                acc.last_error = error
                acc.last_error_at = utcnow()
            if success:
                acc.last_success_at = utcnow()
                acc.last_error = None
            acc.last_check_at = utcnow()
            for k, v in fields.items():
                setattr(acc, k, v)

    # ------------------------------------------------------------------
    def start_login(self, account_id: int, mark_waiting: bool = True) -> None:
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if not acc:
                return
            settings = st.get_all(s)
            label, profile = acc.display_name, str(resolve_profile_dir(self.cfg, acc))
            was_ready = acc.session_status == SessionStatus.READY
        if self.manager.is_busy(account_id):
            self._set(account_id, message="Browser is busy with a monitoring task. Try again when it finishes.")
            return
        existing = self.manager.get(account_id)
        if existing and existing.headless:
            self.manager.close(account_id)  # need a visible window for manual interaction
        try:
            purpose = "login" if mark_waiting else "interactive"
            session = self.manager.open(account_id, label, profile, purpose, browser_options(settings),
                                        force_visible=True)
        except ProfileBusyError as exc:
            self._set(account_id, message=f"Cannot open browser: {exc}")
            activity.warning("account", f"Open browser for {label} refused: {exc}", account_id=account_id)
            return
        except Exception as exc:
            self._set(account_id, SessionStatus.ERROR, f"Chrome failed to start: {str(exc)[:300]}",
                      error=str(exc)[:500])
            activity.error("browser", f"Chrome failed to start for {label}: {exc}", account_id=account_id)
            return

        target_url = MARKETPLACE_HOME if (was_ready and not mark_waiting) else FACEBOOK_HOME
        try:
            session.driver.get(target_url)
        except Exception as exc:  # keep window open regardless
            log.warning("Navigation failed for %s: %s", label, exc)

        if mark_waiting:
            session.activity = "waiting for manual login"
            timeout = settings["login_timeout_minutes"]
            deadline = utcnow() + timedelta(minutes=timeout) if timeout else None
            already = _has_login_cookie(session.driver)
            msg = ("Browser opened. Log in manually in the Chrome window and complete any security verification, "
                   "then click 'Confirm Login'.")
            if already:
                msg = "Browser opened and this profile appears to be logged in already. Click 'Confirm Login' to verify."
            if deadline:
                msg += f" Login timeout: {timeout} min."
            self._set(account_id, SessionStatus.WAITING_LOGIN, msg, login_started_at=utcnow(), login_deadline=deadline)
            activity.info("account", f"Opened browser for manual login: {label}", account_id=account_id)
        else:
            session.activity = "interactive browser"
            activity.info("account", f"Opened visible browser for {label}", account_id=account_id)

    # ------------------------------------------------------------------
    def confirm_login(self, account_id: int) -> None:
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if not acc:
                return
            settings = st.get_all(s)
            label = acc.display_name
        session = self.manager.get(account_id)
        if session is None:
            self._set(account_id, SessionStatus.UNVERIFIED,
                      "The browser window is not open. Click 'Open Browser / Login' first.")
            return
        if not session.use_lock.acquire(blocking=False):
            self._set(account_id, message="Browser is busy; try again in a moment.")
            return
        try:
            session.activity = "verifying login"
            res = navigate_and_classify(session.driver, MARKETPLACE_HOME, browser_options(settings))
        finally:
            session.activity = "idle"
            session.use_lock.release()

        if res.state in SUCCESS:
            self._set(account_id, SessionStatus.READY,
                      "Session Ready. Facebook Marketplace is accessible. The login session is saved in this account's persistent profile and will be reused for future monitoring.",
                      success=True, login_deadline=None)
            activity.info("account", f"Login confirmed for {label}: Marketplace accessible", account_id=account_id)
            if settings.get("headless", False):
                self.manager.close(account_id)
                log.info("Closed visible manual login browser for %s to enable headless monitoring", label)
            else:
                session.purpose = "idle"
        elif res.state in NEEDS_ATTENTION:
            self._set(account_id, SessionStatus.WAITING_LOGIN,
                      f"Security challenge detected ({res.detail}). Please complete the verification in the open Chrome window. The browser remains open for troubleshooting; click 'Confirm Login / Continue' once finished.",
                      error=res.detail)
            activity.warning("account", f"Login confirm for {label}: {res.detail}", account_id=account_id)
        elif res.state == PageState.LOGIN_REQUIRED:
            self._set(account_id, SessionStatus.WAITING_LOGIN,
                      "Facebook still requires login. Please finish signing in inside the open Chrome window, then click 'Confirm Login / Continue'. The browser remains open.")
        else:
            self._set(account_id, SessionStatus.WAITING_LOGIN,
                      f"Could not confirm Marketplace access ({res.detail}). The browser remains open for manual troubleshooting. Complete verification and click 'Confirm Login / Continue' again.",
                      error=res.detail)

    # ------------------------------------------------------------------
    def verify_session(self, account_id: int) -> None:
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if not acc:
                return
            settings = st.get_all(s)
            label, profile = acc.display_name, str(resolve_profile_dir(self.cfg, acc))
        opened_here = not self.manager.is_open(account_id)
        try:
            session = self.manager.open(account_id, label, profile, "verify", browser_options(settings))
        except ProfileBusyError as exc:
            self._set(account_id, message=f"Cannot verify now: {exc}")
            return
        except Exception as exc:
            self._set(account_id, SessionStatus.ERROR, f"Chrome failed to start: {str(exc)[:300]}",
                      error=str(exc)[:500])
            activity.error("browser", f"Chrome failed to start for {label}: {exc}", account_id=account_id)
            return
        if not session.use_lock.acquire(blocking=False):
            self._set(account_id, message="Browser is busy with another task; verification skipped.")
            return
        try:
            session.activity = "verifying session"
            res = navigate_and_classify(session.driver, MARKETPLACE_HOME, browser_options(settings))
        finally:
            session.activity = "idle"
            session.use_lock.release()

        if res.state in SUCCESS:
            self._set(account_id, SessionStatus.READY, "Session verified: Marketplace is accessible.", success=True)
            activity.info("account", f"Session verified for {label}", account_id=account_id)
        elif res.state == PageState.LOGIN_REQUIRED:
            self._set(account_id, SessionStatus.EXPIRED,
                      "Login required. Click 'Open Browser / Login' and sign in manually.", error=res.detail)
            activity.warning("account", f"{label}: login required", account_id=account_id)
        elif res.state in NEEDS_ATTENTION:
            self._set(account_id, SessionStatus.NEEDS_ATTENTION,
                      f"{res.detail}. Open the browser and resolve it manually; the account will not be used "
                      "until it is verified again.", error=res.detail)
            activity.error("account", f"{label}: {res.detail}", account_id=account_id)
        else:
            self._set(account_id, SessionStatus.ERROR, f"Verification failed: {res.detail}", error=res.detail)
            activity.warning("account", f"{label}: verification failed ({res.detail})", account_id=account_id)

        current = self.manager.get(account_id)
        if current and (opened_here and (not settings["keep_browsers_open"] or res.state not in SUCCESS)
                        and current.headless):
            self.manager.close(account_id)
        elif current and opened_here and not settings["keep_browsers_open"]:
            self.manager.close(account_id)

    # ------------------------------------------------------------------
    def close_browser(self, account_id: int) -> None:
        if self.manager.is_busy(account_id):
            self._set(account_id, message="Browser is busy with a task; it will be closed after it finishes.")
            return
        closed = self.manager.close(account_id)
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if acc and acc.session_status == SessionStatus.WAITING_LOGIN:
                acc.session_status = SessionStatus.UNVERIFIED
                acc.status_message = "Browser closed before login was confirmed. Click 'Verify Session' to check."
                acc.login_deadline = None
            elif acc and closed:
                acc.status_message = "Browser closed. The profile and its login are preserved."

    def check_timeouts(self) -> None:
        now = utcnow()
        with session_scope() as s:
            waiting = s.scalars(select(Account).where(Account.session_status == SessionStatus.WAITING_LOGIN)).all()
            for acc in waiting:
                if not self.manager.is_open(acc.id):
                    acc.session_status = SessionStatus.UNVERIFIED
                    acc.status_message = ("The login browser window was closed before login was confirmed. "
                                          "Click 'Verify Session' or 'Open Browser / Login'.")
                    acc.login_deadline = None
                elif acc.login_deadline and now > acc.login_deadline:
                    acc.session_status = SessionStatus.EXPIRED
                    acc.status_message = ("Login timeout reached. The browser window was left open – you can still "
                                          "finish logging in and click 'Confirm Login'.")
                    acc.login_deadline = None
                    activity.warning("account", f"Login timeout for {acc.display_name}", account_id=acc.id)
