"""Job runner: executes a single search cycle end-to-end.

Responsibilities:
1. Load search configuration and apply the Auto Select or specific account assignment.
2. If no eligible account is available, pause/mark the search as waiting and record the reason.
3. Acquire exclusive session for the account via SeleniumFetcher.
4. Build the validated Marketplace URL.
5. Navigate, wait, and classify page state (detect logins, CAPTCHAs, restrictions, rate limits).
6. If blocked or restricted, update account status, pause the search (no silent retry on another account).
7. If successful, extract listings from the page.
8. Filter listings (price, make, model, condition keywords, include/exclude keywords).
9. Optionally fetch listing detail pages for candidate matches if enabled and necessary.
10. Upsert listings and detect duplicates via dedup service.
11. Queue and attempt delivery of Telegram notifications for newly discovered matching listings.
12. Record detailed SearchExecution and update SearchConfiguration statistics.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import activity
from . import account_selector as sel
from . import dedup
from . import extractor
from . import filtering
from . import marketplace_url
from . import settings_store as st
from . import telegram_service
from .account_service import resolve_profile_dir
from .browser_service import BrowserManager, BrowserOptions, SeleniumFetcher
from .page_state import NEEDS_ATTENTION, SUCCESS, PageState
from .profile_lock import ProfileBusyError, holder_info, is_locked
from ..config import Config
from ..db import session_scope
from ..models import (
    Account,
    ExecStatus,
    SearchConfiguration,
    SearchExecution,
    SearchStatus,
    SessionStatus,
    utcnow,
)

log = logging.getLogger("fmbot.job_runner")


def _build_criteria(search: SearchConfiguration, settings: dict) -> filtering.SearchCriteria:
    return filtering.SearchCriteria.from_search(
        search, accept_unknown_price=settings.get("notify_unknown_price", True)
    )


def execute_search_job(
    search_id: int,
    cfg: Config,
    browser_manager: BrowserManager,
    trigger: str = "scheduled",
) -> None:
    """Entry point called by background scheduler worker threads."""
    with session_scope() as s:
        search = s.get(SearchConfiguration, search_id)
        if not search or search.deleted_at is not None:
            return
        if search.is_running:
            log.info("Search %s (%s) is already running; skipping cycle", search.id, search.name)
            return
        search.is_running = True
        s.commit()

    try:
        _run_search(search_id, cfg, browser_manager, trigger)
    finally:
        with session_scope() as s:
            search = s.get(SearchConfiguration, search_id)
            if search:
                search.is_running = False


def _run_search(
    search_id: int,
    cfg: Config,
    browser_manager: BrowserManager,
    trigger: str,
) -> None:
    now = utcnow()
    execution_id: Optional[int] = None

    with session_scope() as s:
        search = s.get(SearchConfiguration, search_id)
        if not search:
            return
        settings = st.get_all(s)

        # 1. Evaluate account eligibility
        ctx = sel.SelectionContext(
            profile_exists=lambda a: resolve_profile_dir(cfg, a).exists(),
            is_locked=lambda a: (
                browser_manager.is_busy(a.id) if browser_manager.is_open(a.id)
                else is_locked(resolve_profile_dir(cfg, a))
            ),
            browser_idle_open=lambda a: browser_manager.is_open(a.id) and not browser_manager.is_busy(a.id),
            runs_today=sel.runs_today_counter(s),
            auto_allowed=settings.get("auto_select_allowed", True),
        )
        res = sel.select_account(s, search, ctx)
        search.last_selection_reason = res.reason

        if not res.account:
            search.status = SearchStatus.WAITING_ACCOUNT
            search.status_message = res.reason
            search.next_run_at = now + timedelta(seconds=settings.get("waiting_recheck_seconds", 120))
            
            # Record an execution entry indicating search is waiting for an account
            exec_entry = SearchExecution(
                search_id=search.id,
                account_id=search.account_id,
                trigger=trigger,
                status=ExecStatus.WAITING_ACCOUNT,
                selection_reason=res.reason,
                started_at=now,
                finished_at=now,
            )
            s.add(exec_entry)
            activity.warning("search", f"Search '{search.name}' waiting: {res.reason}", search_id=search.id, session=s)
            return

        chosen_account_id = res.account.id
        account_name = res.account.display_name
        profile_path = str(resolve_profile_dir(cfg, res.account))
        selection_reason = res.reason
        search.last_account_id = chosen_account_id

        # Create running execution record
        exec_entry = SearchExecution(
            search_id=search.id,
            account_id=chosen_account_id,
            trigger=trigger,
            status=ExecStatus.RUNNING,
            selection_reason=selection_reason,
            started_at=now,
        )
        s.add(exec_entry)
        s.flush()
        execution_id = exec_entry.id

    opts = BrowserOptions(
        headless=settings.get("headless", False),
        page_load_timeout=settings.get("page_load_timeout", 45),
        element_wait_timeout=settings.get("element_wait_timeout", 20),
        max_scroll_rounds=settings.get("max_scroll_rounds", 2),
        scroll_pause_seconds=settings.get("scroll_pause_seconds", 2.5),
    )
    fetcher = SeleniumFetcher(browser_manager)

    # 2. Open browser session and navigate
    try:
        with fetcher.session_for(
            chosen_account_id,
            account_name,
            profile_path,
            opts,
            keep_open=settings.get("keep_browsers_open", True),
        ) as nav:
            with session_scope() as s:
                search = s.get(SearchConfiguration, search_id)
                target_url = marketplace_url.build_search_url(search)
                exec_entry = s.get(SearchExecution, execution_id)
                if exec_entry:
                    exec_entry.url = target_url

            fetch_result = nav.search(target_url)

            with session_scope() as s:
                search = s.get(SearchConfiguration, search_id)
                acc = s.get(Account, chosen_account_id)
                exec_entry = s.get(SearchExecution, execution_id)
                if not search or not acc or not exec_entry:
                    return

                exec_entry.page_state = fetch_result.state.value

                # 3. Check for access blocks/challenges
                if fetch_result.state in NEEDS_ATTENTION or fetch_result.state == PageState.LOGIN_REQUIRED:
                    if fetch_result.state == PageState.LOGIN_REQUIRED:
                        acc.session_status = SessionStatus.EXPIRED
                        acc.status_message = "Session expired. Manual login required."
                    else:
                        acc.session_status = SessionStatus.NEEDS_ATTENTION
                        acc.status_message = fetch_result.detail
                    acc.last_error = fetch_result.detail
                    acc.last_error_at = utcnow()

                    search.status = SearchStatus.PAUSED
                    search.status_message = (
                        f"Search paused: {account_name} encountered access restriction ({fetch_result.detail}). "
                        "Resolve in Account Manager."
                    )
                    exec_entry.status = ExecStatus.BLOCKED
                    exec_entry.error = fetch_result.detail
                    exec_entry.finished_at = utcnow()

                    activity.error(
                        "security",
                        f"Search '{search.name}' halted: {account_name} got {fetch_result.state.value} ({fetch_result.detail})",
                        account_id=acc.id,
                        search_id=search.id,
                        session=s,
                    )
                    return

                if fetch_result.state not in SUCCESS:
                    # Technical / recoverable failure
                    exec_entry.status = ExecStatus.FAILED
                    exec_entry.error = fetch_result.detail
                    exec_entry.finished_at = utcnow()

                    search.consecutive_failures += 1
                    max_fail = settings.get("max_consecutive_failures", 5)
                    if search.consecutive_failures >= max_fail:
                        search.status = SearchStatus.FAILED
                        search.status_message = (
                            f"Failed {search.consecutive_failures} consecutive times. Last error: {fetch_result.detail}"
                        )
                    else:
                        retry_sec = settings.get("retry_backoff_seconds", 120)
                        search.next_run_at = utcnow() + timedelta(seconds=retry_sec)
                        search.status_message = f"Temporary error ({fetch_result.detail}); retrying in {retry_sec}s"

                    activity.warning(
                        "browser",
                        f"Search '{search.name}' fetch failed ({fetch_result.detail})",
                        search_id=search.id,
                        session=s,
                    )
                    return

                # Page successfully loaded
                acc.session_status = SessionStatus.READY
                acc.last_success_at = utcnow()
                acc.status_message = "Operating normally."

                # 4. Extract listings from HTML
                raw_listings = extractor.extract_listings(fetch_result.html)
                exec_entry.found_count = len(raw_listings)

                # Build a set of all unique URLs seen this run for stock tracking
                seen_urls_this_run: set[str] = {item["url"] for item in raw_listings if item.get("url")}

                criteria = _build_criteria(search, settings)
                matched_items = []
                unmatched_items = []  # track unmatched so we can still upsert for URL inventory

                # Filter each listing
                max_details = settings.get("max_detail_pages_per_run", 5) if search.fetch_details else 0
                detail_fetches_done = 0

                for item in raw_listings:
                    f_res = filtering.evaluate(item, criteria)

                    # If candidate matches price/make but needs description to confirm condition/keywords
                    if not f_res.matched and f_res.needs_details and detail_fetches_done < max_details:
                        detail_res = nav.detail(item["url"])
                        if detail_res.state in SUCCESS:
                            detail_info = extractor.extract_detail(detail_res.html)
                            if detail_info.get("description"):
                                item["description"] = detail_info["description"]
                            if detail_info.get("title") and not item.get("title"):
                                item["title"] = detail_info["title"]
                            detail_fetches_done += 1
                            f_res = filtering.evaluate(item, criteria)

                    if f_res.matched:
                        matched_items.append((item, f_res.summary))
                    else:
                        unmatched_items.append(item)

                exec_entry.matched_count = len(matched_items)

                # 5. Database upsert & notification queueing
                new_count = 0
                restocked_count = 0  # previously-seen URLs that reappear (possible re-stock)
                notifications_to_send = []
                scope = settings.get("dedup_scope", "global")
                renotify_drop = settings.get("renotify_price_drop", False)

                for item, match_reason in matched_items:
                    u_res = dedup.upsert_listing(
                        s, item, search.id, acc.id, matched=True, match_reason=match_reason
                    )
                    if u_res.new_listing:
                        new_count += 1
                    elif u_res.new_for_search:
                        # Listing exists globally but is new for THIS search — possible re-stock
                        restocked_count += 1

                    # Notification check
                    should_notify = search.notify_telegram and settings.get("telegram_enabled", False)
                    if should_notify:
                        # Case 1: First time discovered for this scope
                        d_key = dedup.notification_key(u_res.listing.id, search.id, scope, kind="new")
                        notif = dedup.create_notification_once(
                            s,
                            dedup_key=d_key,
                            kind="new",
                            listing_id=u_res.listing.id,
                            search_id=search.id,
                            account_id=acc.id,
                            execution_id=execution_id,
                        )
                        if notif:
                            notifications_to_send.append((notif, None))

                        # Case 2: Price drop
                        elif (
                            renotify_drop
                            and u_res.previous_price_cents is not None
                            and u_res.listing.price_cents is not None
                            and u_res.listing.price_cents < u_res.previous_price_cents
                        ):
                            drop_key = dedup.notification_key(
                                u_res.listing.id,
                                search.id,
                                scope,
                                kind="price_drop",
                                price_cents=u_res.listing.price_cents,
                            )
                            drop_notif = dedup.create_notification_once(
                                s,
                                dedup_key=drop_key,
                                kind="price_drop",
                                listing_id=u_res.listing.id,
                                search_id=search.id,
                                account_id=acc.id,
                                execution_id=execution_id,
                            )
                            if drop_notif:
                                notifications_to_send.append((drop_notif, u_res.previous_price_cents))

                # Also upsert unmatched listings so the URL inventory is always tracked per search.
                # This lets us detect when a previously-absent URL reappears (re-stocked item).
                for item in unmatched_items:
                    dedup.upsert_listing(
                        s, item, search.id, acc.id, matched=False, match_reason="not matched"
                    )

                exec_entry.new_count = new_count
                exec_entry.status = ExecStatus.SUCCESS
                exec_entry.finished_at = utcnow()

                # Update search schedule
                search.last_run_at = utcnow()
                search.consecutive_failures = 0
                search.status = SearchStatus.ACTIVE
                search.status_message = (
                    f"Last run completed successfully: found {len(raw_listings)} "
                    f"({len(seen_urls_this_run)} unique URLs), "
                    f"matched {len(matched_items)}, new {new_count}"
                    + (f", restocked {restocked_count}" if restocked_count else "") + "."
                )
                search.next_run_at = utcnow() + timedelta(minutes=search.interval_minutes)

                s.flush()

                # 6. Dispatch notifications
                notified_count = 0
                if notifications_to_send:
                    tg_client = telegram_service.build_client(s)
                    for n, prev_price in notifications_to_send:
                        if telegram_service.deliver(s, n, tg_client, previous_price_cents=prev_price):
                            notified_count += 1
                    s.flush()

                exec_entry.notified_count = notified_count

                restock_note = f", {restocked_count} possibly restocked" if restocked_count else ""
                activity.info(
                    "search",
                    f"Search '{search.name}' finished: {len(raw_listings)} listings seen "
                    f"({len(seen_urls_this_run)} unique URLs), "
                    f"{len(matched_items)} matched, {new_count} new{restock_note}, {notified_count} notified.",
                    search_id=search.id,
                    account_id=acc.id,
                    session=s,
                )

    except ProfileBusyError as exc:
        with session_scope() as s:
            search = s.get(SearchConfiguration, search_id)
            if search:
                search.status = SearchStatus.WAITING_ACCOUNT
                search.status_message = f"Account busy: {exc}"
                search.next_run_at = utcnow() + timedelta(seconds=60)
            if execution_id:
                exec_entry = s.get(SearchExecution, execution_id)
                if exec_entry:
                    exec_entry.status = ExecStatus.SKIPPED
                    exec_entry.error = str(exc)
                    exec_entry.finished_at = utcnow()
        log.warning("Profile busy during search %s: %s", search_id, exc)

    except Exception as exc:
        log.exception("Unexpected error executing search %s", search_id)
        with session_scope() as s:
            search = s.get(SearchConfiguration, search_id)
            if search:
                search.consecutive_failures += 1
                search.status_message = f"Execution error: {str(exc)[:250]}"
                search.next_run_at = utcnow() + timedelta(seconds=120)
            if execution_id:
                exec_entry = s.get(SearchExecution, execution_id)
                if exec_entry:
                    exec_entry.status = ExecStatus.FAILED
                    exec_entry.error = str(exc)[:500]
                    exec_entry.finished_at = utcnow()
        activity.error("search", f"Search ID {search_id} failed unexpectedly: {exc}", search_id=search_id)
