"""Tampermonkey Bridge Service.

Handles job lifecycle, agent heartbeats, and result ingestion for
dashboard-controlled browser userscripts.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import activity
from . import dedup
from . import extractor
from . import filtering
from . import marketplace_url
from . import settings_store as st
from . import telegram_service
from ..config import Config
from ..models import (
    ExecStatus,
    Listing,
    SearchConfiguration,
    SearchExecution,
    SearchListing,
    SearchStatus,
    TmAgent,
    TmJob,
    TmJobStatus,
    utcnow,
)

log = logging.getLogger("fmbot.tm_service")

# Exact radius options available in Facebook Marketplace location modal dropdown:
STANDARD_KM_OPTIONS = [1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 311, 500]


def snap_radius_km(radius_val: Optional[int], is_miles: bool = True) -> tuple[int, str]:
    """Snap a requested radius to Facebook's closest available dropdown option."""
    if not radius_val or radius_val <= 0:
        km = 5
    elif is_miles:
        km = int(round(radius_val * 1.60934))
    else:
        km = int(radius_val)

    snapped = min(STANDARD_KM_OPTIONS, key=lambda x: abs(x - km))
    label = f"{snapped} kilometer" if snapped == 1 else f"{snapped} kilometers"
    return snapped, label


def enqueue_job(
    session: Session,
    search_id: int,
    trigger: str = "scheduled",
    force: bool = False,
) -> Optional[TmJob]:
    """Enqueue a new Tampermonkey search job for the given search configuration."""
    search = session.get(SearchConfiguration, search_id)
    if not search or search.deleted_at is not None:
        return None

    # Check if job is already pending or running
    if not force and trigger != "manual":
        existing = session.scalar(
            select(TmJob.id).where(
                TmJob.search_id == search_id,
                TmJob.status.in_([TmJobStatus.PENDING, TmJobStatus.CLAIMED, TmJobStatus.RUNNING]),
            )
        )
        if existing:
            log.info("Search %s already has active job %s; skipping enqueue", search_id, existing)
            return None
    else:
        # Cancel any previous active/pending jobs for this search configuration so manual run takes precedence
        old_jobs = session.scalars(
            select(TmJob).where(
                TmJob.search_id == search_id,
                TmJob.status.in_([TmJobStatus.PENDING, TmJobStatus.CLAIMED, TmJobStatus.RUNNING]),
            )
        ).all()
        for oj in old_jobs:
            oj.status = TmJobStatus.EXPIRED
            oj.error = "Superseded by manual trigger"
            oj.finished_at = utcnow()

        # Also expire any other pending scheduled jobs so this manual search gets immediate full priority
        other_pending = session.scalars(
            select(TmJob)
            .join(SearchExecution, SearchExecution.id == TmJob.execution_id, isouter=True)
            .where(
                TmJob.status == TmJobStatus.PENDING,
                SearchExecution.trigger != "manual",
            )
        ).all()
        for pj in other_pending:
            pj.status = TmJobStatus.EXPIRED
            pj.error = f"Deferred for manual run of search #{search_id}"
            pj.finished_at = utcnow()

    snapped_km, radius_label = snap_radius_km(search.radius_miles, is_miles=True)

    # Search term fallback
    terms = search.search_terms.strip() if search.search_terms else ""
    if not terms and (search.make or search.model):
        terms = f"{search.make or ''} {search.model or ''}".strip()

    # Build exact Facebook Marketplace search URL
    target_url = None
    try:
        target_url = marketplace_url.build_search_url(search)
    except Exception as exc:
        log.warning("Could not build target_url for search %s: %s", search.id, exc)

    payload_data = {
        "search_id": search.id,
        "search_name": search.name,
        "search_terms": terms,
        "target_url": target_url,
        "make": search.make,
        "model": search.model,
        "location": search.location or "",
        "radius_km": snapped_km,
        "radius_label": radius_label,
        "min_price": search.min_price,
        "max_price": search.max_price,
        "vehicle_condition": search.vehicle_condition or "any",
        "sort_by": search.sort_by or "newest",
    }

    # Create SearchExecution tracking row
    exec_entry = SearchExecution(
        search_id=search.id,
        account_id=search.account_id,
        trigger=trigger,
        status=ExecStatus.RUNNING,
        started_at=utcnow(),
        url=target_url,
        selection_reason="Assigned to Tampermonkey browser agent",
    )
    session.add(exec_entry)
    session.flush()

    job = TmJob(
        search_id=search.id,
        execution_id=exec_entry.id,
        status=TmJobStatus.PENDING,
        payload=json.dumps(payload_data),
        created_at=utcnow(),
    )
    session.add(job)
    search.is_running = True
    session.commit()

    activity.info(
        "search",
        f"Enqueued Tampermonkey search job #{job.id} for '{search.name}'",
        search_id=search.id,
        session=session,
    )
    return job


def claim_next_job(session: Session, agent_id: str) -> Optional[dict[str, Any]]:
    """Atomically claim the oldest pending job for a Tampermonkey agent, or resume active job."""
    reap_stale_jobs(session)

    # Check if agent kill-switch / pause is active in settings
    is_paused = st.get(session, "tm_agent_paused")
    if is_paused:
        return None

    # Check if this agent already has an active claimed job (e.g. browser navigated to target_url)
    agent = session.scalar(select(TmAgent).where(TmAgent.agent_id == agent_id))
    job = None
    if agent and agent.current_job_id:
        active_job = session.get(TmJob, agent.current_job_id)
        if active_job and active_job.status == TmJobStatus.CLAIMED:
            job = active_job

    if not job:
        job = session.scalar(
            select(TmJob)
            .join(SearchExecution, SearchExecution.id == TmJob.execution_id, isouter=True)
            .where(TmJob.status == TmJobStatus.PENDING)
            .order_by(
                case((SearchExecution.trigger == "manual", 0), else_=1),
                TmJob.created_at.asc(),
            )
            .with_for_update()
        )
    if not job:
        return None

    job.status = TmJobStatus.CLAIMED
    job.agent_id = agent_id
    if not job.claimed_at:
        job.claimed_at = utcnow()
    job.progress_step = "Job running in browser"

    # Update or create agent record
    if not agent:
        agent = TmAgent(
            agent_id=agent_id,
            display_name=f"Agent {agent_id}",
            created_at=utcnow(),
        )
        session.add(agent)

    agent.status = "busy"
    agent.current_job_id = job.id
    agent.last_heartbeat_at = utcnow()
    agent.updated_at = utcnow()

    session.commit()

    payload = json.loads(job.payload)

    # Query listings that already have details memorized
    known_listings = session.scalars(
        select(Listing).where(
            (Listing.description.is_not(None))
            | (Listing.seller_name.is_not(None))
            | (Listing.condition.is_not(None))
        )
    ).all()
    memorized_cache = {
        l.url: {
            "title": l.title,
            "description": l.description,
            "condition": l.condition,
            "seller_name": l.seller_name,
            "location": l.location,
            "price_text": l.price_text,
            "price_cents": l.price_cents,
        }
        for l in known_listings if l.url
    }

    return {
        "job_id": job.id,
        "search_id": job.search_id,
        "execution_id": job.execution_id,
        "memorized_cache": memorized_cache,
        **payload,
    }


def update_progress(session: Session, job_id: int, step: str) -> bool:
    """Record current execution step of a running job."""
    job = session.get(TmJob, job_id)
    if not job:
        return False
    job.progress_step = step[:120]
    session.commit()
    return True


def ingest_job_results(
    session: Session,
    cfg: Config,
    job_id: int,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Ingest, filter, dedup and notify listings returned by Tampermonkey."""
    job = session.get(TmJob, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    search = session.get(SearchConfiguration, job.search_id)
    exec_entry = session.get(SearchExecution, job.execution_id) if job.execution_id else None
    settings = st.get_all(session)

    now = utcnow()
    raw_listings: list[dict[str, Any]] = []

    # 1. Parse listings: prioritize client-side extracted items (contains details, condition, seller)
    listings_by_url: dict[str, dict[str, Any]] = {}

    if "listings" in data and isinstance(data["listings"], list):
        for item in data["listings"]:
            if isinstance(item, dict) and item.get("url"):
                can_url = extractor.canonical_item_url(item["url"])
                price_cents = item.get("price_cents")
                if price_cents is None and item.get("price_text"):
                    price_cents = filtering.parse_price_cents(item.get("price_text"))
                listings_by_url[can_url] = {
                    "fb_item_id": item.get("fb_item_id"),
                    "url": can_url,
                    "title": (item.get("title") or "").strip()[:300],
                    "price_text": item.get("price_text"),
                    "price_cents": price_cents,
                    "location": item.get("location"),
                    "mileage": item.get("mileage"),
                    "condition": item.get("condition"),
                    "description": item.get("description"),
                    "seller_name": item.get("seller_name"),
                    "posted_text": item.get("posted_text"),
                    "image_url": item.get("image_url")[:1000] if item.get("image_url") else None,
                }

    raw_html = data.get("html")
    if raw_html:
        html_listings = extractor.extract_listings(raw_html)
        for h_item in html_listings:
            url = h_item.get("url")
            if not url:
                continue
            if url not in listings_by_url:
                listings_by_url[url] = h_item
            else:
                existing = listings_by_url[url]
                for k, v in h_item.items():
                    if v and not existing.get(k):
                        existing[k] = v

    raw_listings = list(listings_by_url.values())

    found_count = len(raw_listings)
    if exec_entry:
        exec_entry.found_count = found_count
        exec_entry.url = data.get("url")
        exec_entry.page_state = data.get("page_state", "success")

    # 2. Filter listings against criteria
    criteria = filtering.SearchCriteria.from_search(
        search,
        accept_unknown_price=settings.get("notify_unknown_price", True),
    ) if search else None

    seen_urls_this_run: set[str] = {item["url"] for item in raw_listings if item.get("url")}
    matched_items = []
    unmatched_items = []
    if criteria:
        for item in raw_listings:
            f_res = filtering.evaluate(item, criteria)
            if f_res.matched:
                matched_items.append((item, f_res.summary))
            else:
                unmatched_items.append(item)
    else:
        unmatched_items = list(raw_listings)

    matched_count = len(matched_items)
    if exec_entry:
        exec_entry.matched_count = matched_count

    # 3. Deduplication and Telegram notifications
    new_count = 0
    restocked_count = 0
    notifications_to_send = []
    scope = settings.get("dedup_scope", "global")
    renotify_drop = settings.get("renotify_price_drop", False)

    for item, match_reason in matched_items:
        u_res = dedup.upsert_listing(
            session,
            item,
            search.id if search else 0,
            account_id=None,
            matched=True,
            match_reason=match_reason,
        )
        if u_res.new_listing:
            new_count += 1
        elif u_res.new_for_search:
            restocked_count += 1

        should_notify = search and search.notify_telegram and settings.get("telegram_enabled", False)
        if should_notify:
            d_key = dedup.notification_key(u_res.listing.id, search.id, scope, kind="new")
            notif = dedup.create_notification_once(
                session,
                dedup_key=d_key,
                kind="new",
                listing_id=u_res.listing.id,
                search_id=search.id,
                account_id=None,
                execution_id=exec_entry.id if exec_entry else None,
            )
            if notif:
                notifications_to_send.append((notif, None))
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
                    session,
                    dedup_key=drop_key,
                    kind="price_drop",
                    listing_id=u_res.listing.id,
                    search_id=search.id,
                    account_id=None,
                    execution_id=exec_entry.id if exec_entry else None,
                )
                if drop_notif:
                    notifications_to_send.append((drop_notif, u_res.previous_price_cents))

    # Also upsert unmatched listings to maintain full unique-URL inventory for stock detection
    if search:
        for item in unmatched_items:
            dedup.upsert_listing(
                session, item, search.id, account_id=None, matched=False, match_reason="not matched"
            )

    # Send queued notifications
    notified_count = 0
    if notifications_to_send:
        tg_client = telegram_service.build_client(session)
        for notif, old_price in notifications_to_send:
            try:
                if telegram_service.deliver(session, notif, tg_client, previous_price_cents=old_price):
                    notified_count += 1
            except Exception as e:
                log.warning("Failed to send telegram notification %s: %s", notif.id, e)
        session.flush()

    # 4. Finalize records
    if exec_entry:
        exec_entry.new_count = new_count
        exec_entry.notified_count = notified_count
        exec_entry.status = ExecStatus.SUCCESS
        exec_entry.finished_at = now

    if search:
        search.is_running = False
        search.consecutive_failures = 0
        search.last_run_at = now
        search.next_run_at = now + timedelta(minutes=search.interval_minutes)
        search.status = SearchStatus.ACTIVE
        restock_msg = f", {restocked_count} restocked" if restocked_count else ""
        search.status_message = (
            f"TM Agent scraped {found_count} items ({len(seen_urls_this_run)} unique URLs, "
            f"{matched_count} matched, {new_count} new{restock_msg}) at "
            f"{now.strftime('%H:%M:%S')} UTC"
        )

    job.status = TmJobStatus.DONE
    job.finished_at = now
    job.progress_step = f"Completed ({found_count} found, {matched_count} matched)"
    job.result_summary = json.dumps({
        "found_count": found_count,
        "matched_count": matched_count,
        "new_count": new_count,
        "notified_count": notified_count,
    })

    # Release agent
    if job.agent_id:
        agent = session.scalar(select(TmAgent).where(TmAgent.agent_id == job.agent_id))
        if agent:
            agent.status = "idle"
            agent.current_job_id = None
            agent.updated_at = now

    session.commit()

    restock_note = f", {restocked_count} restocked" if restocked_count else ""
    activity.info(
        "search",
        f"Search '{search.name if search else job_id}' cycle finished via Tampermonkey: "
        f"{found_count} found ({len(seen_urls_this_run)} unique URLs), {matched_count} matched, "
        f"{new_count} new{restock_note}, {notified_count} notified",
        search_id=search.id if search else None,
        session=session,
    )
    return {
        "found_count": found_count,
        "matched_count": matched_count,
        "new_count": new_count,
        "notified_count": notified_count,
    }


def fail_job(session: Session, job_id: int, error_msg: str, step: Optional[str] = None) -> None:
    """Record a failure reported by Tampermonkey."""
    job = session.get(TmJob, job_id)
    if not job:
        return

    now = utcnow()
    job.status = TmJobStatus.FAILED
    job.error = error_msg
    job.progress_step = f"Failed at {step or 'execution'}: {error_msg[:60]}"
    job.finished_at = now

    search = session.get(SearchConfiguration, job.search_id)
    if search:
        search.is_running = False
        search.consecutive_failures += 1
        search.status_message = f"TM Agent error: {error_msg[:120]}"

    exec_entry = session.get(SearchExecution, job.execution_id) if job.execution_id else None
    if exec_entry:
        exec_entry.status = ExecStatus.FAILED
        exec_entry.error = error_msg
        exec_entry.finished_at = now

    if job.agent_id:
        agent = session.scalar(select(TmAgent).where(TmAgent.agent_id == job.agent_id))
        if agent:
            agent.status = "idle"
            agent.current_job_id = None
            agent.updated_at = now

    session.commit()
    activity.warning(
        "browser",
        f"TM Job #{job_id} failed ({step or 'unknown step'}): {error_msg}",
        search_id=job.search_id,
        session=session,
    )


def reap_stale_jobs(session: Session, timeout_seconds: int = 180) -> int:
    """Expire jobs claimed or running longer than timeout_seconds without completion, or unclaimed pending jobs."""
    from sqlalchemy import or_, and_
    cutoff = utcnow() - timedelta(seconds=timeout_seconds)
    pending_cutoff = utcnow() - timedelta(seconds=900)  # Allow queued searches up to 15 min to be picked up
    stale_jobs = session.scalars(
        select(TmJob).where(
            or_(
                and_(
                    TmJob.status.in_([TmJobStatus.CLAIMED, TmJobStatus.RUNNING]),
                    TmJob.claimed_at < cutoff,
                ),
                and_(
                    TmJob.status == TmJobStatus.PENDING,
                    TmJob.created_at < pending_cutoff,
                ),
            )
        )
    ).all()

    count = 0
    for job in stale_jobs:
        job.status = TmJobStatus.EXPIRED
        if job.status == TmJobStatus.PENDING:
            job.error = f"Unclaimed pending job expired after {timeout_seconds}s (no browser agent connected)"
        else:
            job.error = f"Agent timed out after {timeout_seconds}s without completion"
        job.finished_at = utcnow()

        search = session.get(SearchConfiguration, job.search_id)
        if search:
            search.is_running = False
            search.status_message = "Search job expired: no active browser agent."

        exec_entry = session.get(SearchExecution, job.execution_id) if job.execution_id else None
        if exec_entry:
            exec_entry.status = ExecStatus.FAILED
            exec_entry.error = "Tampermonkey agent timeout"
            exec_entry.finished_at = utcnow()

        count += 1

    if count:
        session.commit()
        log.warning("Reaped %d stale Tampermonkey jobs", count)
    return count


def record_heartbeat(
    session: Session,
    agent_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Record heartbeat from Tampermonkey userscript."""
    now = utcnow()
    agent = session.scalar(select(TmAgent).where(TmAgent.agent_id == agent_id))
    if not agent:
        agent = TmAgent(
            agent_id=agent_id,
            display_name=data.get("display_name", "Browser Agent"),
            created_at=now,
        )
        session.add(agent)

    agent.fb_user = data.get("fb_user") or agent.fb_user
    agent.current_url = data.get("current_url")
    agent.last_heartbeat_at = now
    if agent.status != "busy":
        agent.status = "idle"
    agent.updated_at = now

    is_paused = st.get(session, "tm_agent_paused")
    pending_count = session.scalar(
        select(func.count(TmJob.id)).where(TmJob.status == TmJobStatus.PENDING)
    ) or 0

    session.commit()
    return {
        "status": "ok",
        "paused": is_paused,
        "pending_jobs": pending_count,
        "server_time": now.isoformat(),
    }
