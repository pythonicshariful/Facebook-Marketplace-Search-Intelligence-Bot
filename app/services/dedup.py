"""Listing identity, upsert and notification de-duplication.

Listing key
-----------
* Preferred: ``fb:<numeric item id>`` parsed from ``/marketplace/item/<id>``.
* Fallback fingerprint (documented): ``fp:`` + first 32 hex chars of
  SHA-256 over ``canonical_url | normalized title | price_cents | normalized
  location``. The fingerprint changes if the title/price changes, which may
  create a second record – acceptable because it only applies when Facebook
  does not expose an item id.

Notification dedup key (UNIQUE column on ``notifications``)
-----------------------------------------------------------
* scope ``global``     -> ``new:<listing_id>`` (one alert per listing ever)
* scope ``per_search`` -> ``new:<listing_id>:s<search_id>``
* price drop re-notify -> ``drop:<listing_id>:s<search_id>:<price_cents>``

Inserts use SAVEPOINTs; an IntegrityError means another worker already
created the row, so concurrent tasks can never produce duplicates.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .filtering import normalize_text
from ..models import Listing, Notification, NotifyStatus, SearchListing, utcnow


def listing_key(raw: dict[str, Any]) -> tuple[str, str]:
    if raw.get("fb_item_id"):
        return f"fb:{raw['fb_item_id']}", "fb_id"
    basis = "|".join([
        (raw.get("url") or "").lower(),
        normalize_text(raw.get("title")),
        str(raw.get("price_cents") if raw.get("price_cents") is not None else ""),
        normalize_text(raw.get("location")),
    ])
    return "fp:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32], "fingerprint"


@dataclass
class UpsertResult:
    listing: Listing
    link: SearchListing
    new_listing: bool          # first time this application has ever seen it
    new_for_search: bool       # first time this search has seen it
    previous_price_cents: Optional[int]


_UPDATABLE = ("title", "price_text", "price_cents", "location", "mileage", "condition",
              "description", "image_url", "posted_text", "seller_name")


def upsert_listing(session: Session, raw: dict[str, Any], search_id: int, account_id: Optional[int],
                   matched: bool, match_reason: str) -> UpsertResult:
    key, key_type = listing_key(raw)
    now = utcnow()
    listing = session.scalar(select(Listing).where(Listing.listing_key == key))
    new_listing = False
    if listing is None:
        try:
            with session.begin_nested():
                listing = Listing(listing_key=key, key_type=key_type, fb_item_id=raw.get("fb_item_id"),
                                  url=raw["url"], first_seen_at=now, last_seen_at=now,
                                  first_account_id=account_id,
                                  **{k: raw.get(k) for k in _UPDATABLE if raw.get(k) is not None})
                session.add(listing)
            new_listing = True
        except IntegrityError:
            listing = session.scalar(select(Listing).where(Listing.listing_key == key))
            if listing is None:  # pragma: no cover
                raise
    previous_price = listing.price_cents
    if not new_listing:
        listing.last_seen_at = now
        for k in _UPDATABLE:
            if raw.get(k) is not None:
                setattr(listing, k, raw[k])

    link = session.scalar(select(SearchListing).where(SearchListing.search_id == search_id,
                                                      SearchListing.listing_id == listing.id))
    new_for_search = False
    if link is None:
        try:
            with session.begin_nested():
                link = SearchListing(search_id=search_id, listing_id=listing.id, account_id=account_id,
                                     matched=matched, match_reason=match_reason,
                                     last_price_cents=listing.price_cents, first_seen_at=now, last_seen_at=now)
                session.add(link)
            new_for_search = True
        except IntegrityError:
            link = session.scalar(select(SearchListing).where(SearchListing.search_id == search_id,
                                                              SearchListing.listing_id == listing.id))
    else:
        previous_price = link.last_price_cents if link.last_price_cents is not None else previous_price
        link.last_seen_at = now
        link.account_id = account_id
        link.matched = matched or link.matched
        link.match_reason = match_reason
        link.last_price_cents = listing.price_cents
    return UpsertResult(listing, link, new_listing, new_for_search,
                        None if new_for_search else previous_price)


def notification_key(listing_id: int, search_id: int, scope: str, kind: str = "new",
                     price_cents: Optional[int] = None) -> str:
    if kind == "price_drop":
        return f"drop:{listing_id}:s{search_id}:{price_cents}"
    if scope == "per_search":
        return f"new:{listing_id}:s{search_id}"
    return f"new:{listing_id}"


def create_notification_once(session: Session, *, dedup_key: str, kind: str, listing_id: int,
                             search_id: int, account_id: Optional[int],
                             execution_id: Optional[int]) -> Optional[Notification]:
    """Insert a pending notification unless the dedup key already exists."""
    if session.scalar(select(Notification.id).where(Notification.dedup_key == dedup_key)):
        return None
    try:
        with session.begin_nested():
            n = Notification(dedup_key=dedup_key, kind=kind, listing_id=listing_id, search_id=search_id,
                             account_id=account_id, execution_id=execution_id, status=NotifyStatus.PENDING)
            session.add(n)
        return n
    except IntegrityError:
        return None
