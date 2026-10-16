"""Matched Listings viewer blueprint."""
from __future__ import annotations

import math

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, select

from ..db import db
from ..models import Listing, SearchConfiguration, SearchListing

bp = Blueprint("listings", __name__, url_prefix="/listings")

PAGE_SIZE = 25


@bp.route("/")
@login_required
def index():
    search_id = request.args.get("search_id", type=int)
    q = request.args.get("q", "").strip()
    matched_filter = request.args.get("matched", "all")  # 'all', '1' (matched), '0' (unmatched)
    page = max(1, request.args.get("page", 1, type=int))

    # Base query
    stmt = select(Listing)

    if search_id:
        stmt = stmt.join(SearchListing, SearchListing.listing_id == Listing.id).where(SearchListing.search_id == search_id)
        if matched_filter == "1":
            stmt = stmt.where(SearchListing.matched == True)  # noqa: E712
        elif matched_filter == "0":
            stmt = stmt.where(SearchListing.matched == False)  # noqa: E712
    elif matched_filter == "1":
        stmt = stmt.join(SearchListing, SearchListing.listing_id == Listing.id).where(SearchListing.matched == True).distinct()  # noqa: E712
    elif matched_filter == "0":
        stmt = stmt.join(SearchListing, SearchListing.listing_id == Listing.id).where(SearchListing.matched == False).distinct()  # noqa: E712

    if q:
        kw = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Listing.title).like(kw)
            | func.lower(Listing.description).like(kw)
            | func.lower(Listing.location).like(kw)
            | func.lower(Listing.url).like(kw)
        )

    # Count total for current filter
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))

    # Tab counts (All, Matched, Unmatched)
    if search_id:
        cnt_all = db.scalar(select(func.count(SearchListing.id)).where(SearchListing.search_id == search_id)) or 0
        cnt_matched = db.scalar(select(func.count(SearchListing.id)).where(SearchListing.search_id == search_id, SearchListing.matched == True)) or 0  # noqa: E712
        cnt_unmatched = cnt_all - cnt_matched
    else:
        cnt_all = db.scalar(select(func.count(Listing.id))) or 0
        cnt_matched = db.scalar(select(func.count(func.distinct(SearchListing.listing_id))).where(SearchListing.matched == True)) or 0  # noqa: E712
        cnt_unmatched = max(0, cnt_all - cnt_matched)

    # Paginate
    stmt = stmt.order_by(Listing.first_seen_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    listings = db.scalars(stmt).all()

    # Build map of SearchListing details for the current search_id
    search_link_map = {}
    if search_id and listings:
        listing_ids = [l.id for l in listings]
        links = db.scalars(
            select(SearchListing).where(
                SearchListing.search_id == search_id,
                SearchListing.listing_id.in_(listing_ids),
            )
        ).all()
        for lnk in links:
            search_link_map[lnk.listing_id] = lnk

    all_searches = db.scalars(select(SearchConfiguration).where(SearchConfiguration.deleted_at.is_(None)).order_by(SearchConfiguration.name)).all()
    current_search = db.get(SearchConfiguration, search_id) if search_id else None

    return render_template(
        "listings/index.html",
        listings=listings,
        all_searches=all_searches,
        current_search_id=search_id,
        current_search=current_search,
        q=q,
        matched_filter=matched_filter,
        cnt_all=cnt_all,
        cnt_matched=cnt_matched,
        cnt_unmatched=cnt_unmatched,
        search_link_map=search_link_map,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@bp.route("/<int:listing_id>")
@login_required
def detail(listing_id: int):
    listing = db.get(Listing, listing_id)
    if not listing:
        return "Listing not found", 404
    return render_template("listings/detail_modal.html", listing=listing)
