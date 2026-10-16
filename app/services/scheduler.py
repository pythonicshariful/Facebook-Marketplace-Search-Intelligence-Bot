"""Background job scheduler and executor pool.

Architecture:
- Driven by an APScheduler BackgroundScheduler that triggers a periodic "tick"
  (default every 15 seconds).
- The tick queries SQLite for active searches where ``next_run_at <= utcnow()``
  and ``is_running == False``.
- Dispatches due searches to a ``ThreadPoolExecutor`` (sized by ``max_concurrent_jobs``).
- Startup recovery: clears any stale ``is_running`` flags left by an ungraceful crash.
- Housekeeping: periodically triggers Telegram notification retries and login session timeout checks.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from . import activity
from . import job_runner
from . import login_session
from . import settings_store as st
from . import telegram_service
from . import tm_service
from .browser_service import BrowserManager
from ..config import Config
from ..db import session_scope
from ..models import Account, ExecStatus, SearchConfiguration, SearchExecution, SearchStatus, SessionStatus, utcnow

log = logging.getLogger("fmbot.scheduler")


class SearchScheduler:
    def __init__(self, cfg: Config, browser_manager: BrowserManager):
        self.cfg = cfg
        self.browser_manager = browser_manager
        self.login_service = login_session.LoginService(browser_manager, cfg)
        self.scheduler: Optional[BackgroundScheduler] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self._running_searches: set[int] = set()
        self._lock = threading.Lock()
        self._is_active = False

    def start(self) -> None:
        with self._lock:
            if self._is_active:
                return

            self._recover_state()

            with session_scope() as s:
                max_workers = st.get(s, "max_concurrent_jobs")
                tick_interval = self.cfg.SCHEDULER_TICK_SECONDS

            self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="FMBotWorker")
            self.scheduler = BackgroundScheduler(daemon=True)

            # Main search dispatch tick
            self.scheduler.add_job(
                self._tick,
                "interval",
                seconds=tick_interval,
                id="search_dispatcher",
                replace_existing=True,
                max_instances=1,
            )

            # Notification retry & timeout check tick (every 60s)
            self.scheduler.add_job(
                self._housekeeping,
                "interval",
                seconds=60,
                id="scheduler_housekeeping",
                replace_existing=True,
                max_instances=1,
            )

            self.scheduler.start()
            self._is_active = True
            log.info("SearchScheduler started (tick: %ds, workers: %d)", tick_interval, max_workers)
            activity.info("system", f"Monitoring scheduler started with {max_workers} worker threads.")

    def stop(self) -> None:
        with self._lock:
            if not self._is_active:
                return
            log.info("Shutting down SearchScheduler...")
            self._is_active = False

            if self.scheduler:
                try:
                    self.scheduler.shutdown(wait=False)
                except Exception:
                    pass

            if self.executor:
                try:
                    self.executor.shutdown(wait=True, cancel_futures=True)
                except Exception:
                    pass

            # Close open browsers safely and release locks
            self.browser_manager.shutdown_all()

            # Reset running flags in database
            self._recover_state()
            log.info("SearchScheduler stopped cleanly.")
            activity.info("system", "Monitoring scheduler stopped cleanly.")

    def trigger_search_now(self, search_id: int) -> bool:
        """Manually trigger a search immediately from the UI."""
        with self._lock:
            if search_id in self._running_searches:
                return False
            if not self.executor:
                return False

        with session_scope() as s:
            search = s.get(SearchConfiguration, search_id)
            if not search or search.deleted_at is not None:
                return False
            search.next_run_at = utcnow()
            s.commit()

        self._submit_job(search_id, trigger="manual")
        return True

    def trigger_login_flow(self, account_id: int) -> None:
        """Launch browser in background for operator to log in."""
        if not self.executor:
            return
        self.executor.submit(self.login_service.start_login, account_id, True)

    def trigger_open_browser(self, account_id: int) -> None:
        """Launch visible browser for operator interaction without demoting ready session."""
        if not self.executor:
            return
        self.executor.submit(self.login_service.start_login, account_id, False)

    def trigger_confirm_login(self, account_id: int) -> None:
        """Verify session in the open login browser in background."""
        if not self.executor:
            return
        self.executor.submit(self.login_service.confirm_login, account_id)

    def trigger_verify_session(self, account_id: int) -> None:
        """Verify an existing session in background."""
        if not self.executor:
            return
        self.executor.submit(self.login_service.verify_session, account_id)

    def trigger_close_browser(self, account_id: int) -> None:
        """Close browser in background."""
        if not self.executor:
            return
        self.executor.submit(self.login_service.close_browser, account_id)

    # ----------------------------------------------------------------------
    # Internal Dispatcher
    # ----------------------------------------------------------------------
    def _recover_state(self) -> None:
        """Clean up dangling states after application start or unexpected shutdown."""
        try:
            with session_scope() as s:
                # Mark interrupted executions
                s.execute(
                    update(SearchExecution)
                    .where(SearchExecution.status == ExecStatus.RUNNING)
                    .values(
                        status=ExecStatus.INTERRUPTED,
                        error="Application restarted while execution was in progress.",
                        finished_at=utcnow(),
                    )
                )
                # Reset search running flags
                s.execute(
                    update(SearchConfiguration)
                    .where(SearchConfiguration.is_running == True)  # noqa: E712
                    .values(is_running=False)
                )
                # Reset waiting login accounts if browser is closed
                s.execute(
                    update(Account)
                    .where(Account.session_status == SessionStatus.WAITING_LOGIN)
                    .values(
                        session_status=SessionStatus.UNVERIFIED,
                        status_message="Application restarted while waiting for login. Click 'Verify Session'.",
                    )
                )
        except Exception as exc:
            log.warning("State recovery encountered an error: %s", exc)

    def _tick(self) -> None:
        if not self._is_active or not self.executor:
            return

        due_search_ids: list[int] = []
        now = utcnow()

        with session_scope() as s:
            if not self.cfg.SCHEDULER_ENABLED:
                return

            # Find active searches due for monitoring
            stmt = (
                select(SearchConfiguration.id)
                .where(
                    SearchConfiguration.status.in_([SearchStatus.ACTIVE, SearchStatus.WAITING_ACCOUNT]),
                    SearchConfiguration.deleted_at.is_(None),
                    SearchConfiguration.next_run_at <= now,
                    SearchConfiguration.is_running == False,  # noqa: E712
                )
                .order_by(SearchConfiguration.next_run_at)
                .limit(20)
            )
            candidates = s.scalars(stmt).all()

            with self._lock:
                for sid in candidates:
                    if sid not in self._running_searches:
                        due_search_ids.append(sid)

        for sid in due_search_ids:
            self._submit_job(sid, trigger="scheduled")

    def _submit_job(self, search_id: int, trigger: str) -> None:
        with self._lock:
            self._running_searches.add(search_id)

        # Determine active mode: tampermonkey vs selenium
        mode = "tampermonkey"
        try:
            with session_scope() as s:
                mode = st.get(s, "scraper_mode") or getattr(self.cfg, "SCRAPER_MODE", "tampermonkey")
        except Exception:
            mode = getattr(self.cfg, "SCRAPER_MODE", "tampermonkey")

        # 1. Tampermonkey mode: enqueue job into database queue for browser agent
        if mode == "tampermonkey":
            try:
                with session_scope() as s:
                    tm_service.enqueue_job(s, search_id, trigger=trigger, force=(trigger == "manual"))
            except Exception as exc:
                log.exception("Error enqueuing Tampermonkey job for search %s: %s", search_id, exc)
            finally:
                with self._lock:
                    self._running_searches.discard(search_id)
            return

        # 2. Selenium mode: run headless/undetected Chrome driver in worker thread
        def _worker_wrapper():
            try:
                job_runner.execute_search_job(search_id, self.cfg, self.browser_manager, trigger=trigger)
            except Exception as exc:
                log.exception("Unhandled error in search worker %s", search_id)
            finally:
                with self._lock:
                    self._running_searches.discard(search_id)

        try:
            self.executor.submit(_worker_wrapper)
        except Exception as exc:
            with self._lock:
                self._running_searches.discard(search_id)
            log.error("Failed to submit search job %s to thread pool: %s", search_id, exc)

    def _housekeeping(self) -> None:
        try:
            with session_scope() as s:
                # 1. Retry due telegram notifications
                if st.get(s, "telegram_enabled"):
                    sent = telegram_service.retry_due(s)
                    if sent > 0:
                        log.info("Housekeeping: redelivered %d pending Telegram notifications", sent)

                # 2. Reap stale Tampermonkey jobs (> 3 mins)
                tm_service.reap_stale_jobs(s)

            # 3. Check login timeouts for Selenium if used
            if getattr(self.cfg, "SCRAPER_MODE", "tampermonkey") == "selenium":
                self.login_service.check_timeouts()

        except Exception as exc:
            log.warning("Housekeeping tick error: %s", exc)
