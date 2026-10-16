"""Search configuration validation and lifecycle operations."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import dedup, settings_store as st, telegram_service
from .account_service import ValidationError
from .filtering import CONDITION_KEYWORDS, SearchCriteria, evaluate, parse_keywords
from .marketplace_url import SORT_OPTIONS, build_search_url, valid_slug
from ..models import Account, Listing, SearchConfiguration, SearchListing, SearchStatus, utcnow

log = logging.getLogger("fmbot.search_service")

FIELDS = ("name", "search_terms", "make", "model", "location", "location_slug", "radius_miles", "min_price",
          "max_price", "vehicle_condition", "include_keywords", "exclude_keywords", "sort_by",
          "interval_minutes", "fetch_details", "account_mode", "account_id", "notify_telegram")


def _opt_int(value: Any, label: str, lo: int, hi: int, errors: list[str]) -> int | None:
    if value in (None, ""):
        return None
    try:
        v = int(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if not lo <= v <= hi:
        errors.append(f"{label} must be between {lo:,} and {hi:,}.")
    return v


def _bool(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "on", "yes"} if not isinstance(v, bool) else v


def validate(session: Session, form: dict, search_id: int | None = None) -> dict:
    errors: list[str] = []
    d: dict[str, Any] = {}
    d["name"] = " ".join((form.get("name") or "").split())
    if not 2 <= len(d["name"]) <= 120:
        errors.append("Search name must be 2–120 characters.")
    else:
        q = select(SearchConfiguration.id).where(func.lower(SearchConfiguration.name) == d["name"].lower(),
                                                 SearchConfiguration.deleted_at.is_(None))
        if search_id:
            q = q.where(SearchConfiguration.id != search_id)
        if session.scalar(q):
            errors.append(f"A search named '{d['name']}' already exists.")
    for f, n in (("search_terms", 200), ("make", 60), ("model", 60), ("location", 120)):
        d[f] = " ".join((form.get(f) or "").split())[:n] or None
    d["search_terms"] = d["search_terms"] or ""
    if not (d["search_terms"] or d["make"] or d["model"]):
        errors.append("Enter search terms or a vehicle make/model.")
    d["location_slug"] = (form.get("location_slug") or "").strip() or None
    if not valid_slug(d["location_slug"]):
        errors.append("Marketplace location must be a URL slug like 'portland' or a numeric location ID.")
    d["radius_miles"] = _opt_int(form.get("radius_miles"), "Radius", 1, 500, errors)
    d["min_price"] = _opt_int(form.get("min_price"), "Minimum price", 0, 10_000_000, errors)
    d["max_price"] = _opt_int(form.get("max_price"), "Maximum price", 0, 10_000_000, errors)
    if d["min_price"] is not None and d["max_price"] is not None and d["min_price"] > d["max_price"]:
        errors.append("Minimum price cannot exceed maximum price.")
    d["vehicle_condition"] = form.get("vehicle_condition") or "any"
    if d["vehicle_condition"] not in CONDITION_KEYWORDS:
        errors.append("Unknown vehicle condition.")
    d["include_keywords"] = "\n".join(parse_keywords(form.get("include_keywords")))
    d["exclude_keywords"] = "\n".join(parse_keywords(form.get("exclude_keywords")))
    if len(d["include_keywords"]) > 4000 or len(d["exclude_keywords"]) > 4000:
        errors.append("Keyword lists are too long.")
    d["sort_by"] = form.get("sort_by") or "newest"
    if d["sort_by"] not in SORT_OPTIONS:
        errors.append("Unknown sort option.")
    min_iv = st.get(session, "min_interval_minutes")
    iv = _opt_int(form.get("interval_minutes"), "Monitoring interval", 1, 1440, errors)
    d["interval_minutes"] = iv if iv is not None else st.get(session, "default_interval_minutes")
    if d["interval_minutes"] < min_iv:
        errors.append(f"Monitoring interval must be at least {min_iv} minutes (Application Settings → minimum interval).")
    d["fetch_details"] = _bool(form.get("fetch_details", False))
    d["notify_telegram"] = _bool(form.get("notify_telegram", False))
    sel = (form.get("account") or "").strip()
    if sel == "auto":
        d["account_mode"], d["account_id"] = "auto", None
    else:
        d["account_mode"] = "specific"
        try:
            d["account_id"] = int(sel)
        except ValueError:
            d["account_id"] = None
            errors.append("Choose an account or Auto Select.")
        else:
            if not session.get(Account, d["account_id"]):
                errors.append("Selected account does not exist.")
    if not errors:
        class _Tmp:  # validate URL buildability
            pass
        tmp = _Tmp()
        tmp.__dict__.update(d)
        try:
            build_search_url(tmp)
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValidationError(errors)
    return d


def create(session: Session, form: dict) -> SearchConfiguration:
    data = validate(session, form)
    s = SearchConfiguration(**data, status=SearchStatus.ACTIVE, next_run_at=utcnow())
    session.add(s)
    session.flush()
    return s


def update(session: Session, search: SearchConfiguration, form: dict) -> SearchConfiguration:
    data = validate(session, form, search_id=search.id)
    interval_changed = data["interval_minutes"] != search.interval_minutes
    account_changed = (data["account_mode"], data["account_id"]) != (search.account_mode, search.account_id)
    for k, v in data.items():
        setattr(search, k, v)
    if search.status in (SearchStatus.WAITING_ACCOUNT, SearchStatus.FAILED) and account_changed:
        search.status = SearchStatus.ACTIVE
        search.status_message = "Account assignment changed."
        search.next_run_at = utcnow()
    elif interval_changed and search.last_run_at:
        search.next_run_at = max(utcnow(), search.last_run_at + timedelta(minutes=search.interval_minutes))
    session.flush()
    reevaluate_listings(session, search.id)
    return search


def reevaluate_listings(session: Session, search_id: int, send_notifications: bool = True) -> tuple[int, int, int]:
    """Re-evaluate all existing listings associated with search_id using current search criteria.
    Returns (total_evaluated, matched_count, notified_count).
    """
    search = session.get(SearchConfiguration, search_id)
    if not search:
        return 0, 0, 0

    settings = st.get_all(session)
    criteria = SearchCriteria.from_search(
        search,
        accept_unknown_price=settings.get("notify_unknown_price", True),
    )

    links = session.scalars(
        select(SearchListing).where(SearchListing.search_id == search_id)
    ).all()

    total = len(links)
    matched_count = 0
    notifications_to_send = []
    scope = settings.get("dedup_scope", "global")

    for link in links:
        l = link.listing
        if not l:
            continue
        raw = {
            "url": l.url,
            "title": l.title,
            "description": l.description,
            "condition": l.condition,
            "location": l.location,
            "seller_name": l.seller_name,
            "price_text": l.price_text,
            "price_cents": l.price_cents,
            "image_url": l.image_url,
        }
        res = evaluate(raw, criteria)
        link.matched = res.matched
        link.match_reason = res.summary
        if res.matched:
            matched_count += 1
            if send_notifications and search.notify_telegram and settings.get("telegram_enabled", False):
                d_key = dedup.notification_key(l.id, search.id, scope, kind="new")
                notif = dedup.create_notification_once(
                    session,
                    dedup_key=d_key,
                    kind="new",
                    listing_id=l.id,
                    search_id=search.id,
                    account_id=None,
                    execution_id=None,
                )
                if notif:
                    notifications_to_send.append((notif, None))

    session.flush()

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

    return total, matched_count, notified_count


def pause(search: SearchConfiguration, message: str = "Paused by operator.") -> None:
    search.status = SearchStatus.PAUSED
    search.status_message = message


def resume(search: SearchConfiguration) -> None:
    search.status = SearchStatus.ACTIVE
    search.status_message = "Resumed by operator."
    search.consecutive_failures = 0
    search.next_run_at = utcnow()


def duplicate(session: Session, search: SearchConfiguration) -> SearchConfiguration:
    base = f"{search.name} (copy)"
    name, n = base, 2
    while session.scalar(select(SearchConfiguration.id).where(SearchConfiguration.name == name,
                                                              SearchConfiguration.deleted_at.is_(None))):
        name, n = f"{base} {n}", n + 1
    data = {f: getattr(search, f) for f in FIELDS}
    data["name"] = name[:120]
    copy = SearchConfiguration(**data, status=SearchStatus.PAUSED,
                               status_message="Duplicated – review and resume when ready.")
    session.add(copy)
    session.flush()
    return copy


def soft_delete(search: SearchConfiguration) -> None:
    """Historical listings / executions are kept; the search is hidden."""
    search.deleted_at = utcnow()
    search.status = SearchStatus.PAUSED
    search.status_message = "Deleted"
    search.name = f"{search.name} [deleted {search.id}]"[:120]
