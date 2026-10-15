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
    matched_only = request.args.get("matched", "1") == "1"
    page = max(1, request.args.get("page", 1, type=int))

    # Base query
    stmt = select(Listing)

    if search_id:
        stmt = stmt.join(SearchListing, SearchListing.listing_id == Listing.id).where(SearchListing.search_id == search_id)
        if matched_only:
            stmt = stmt.where(SearchListing.matched == True)  # noqa: E712
    elif matched_only:
        stmt = stmt.join(SearchListing, SearchListing.listing_id == Listing.id).where(SearchListing.matched == True).distinct()  # noqa: E712

    if q:
        kw = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Listing.title).like(kw)
            | func.lower(Listing.description).like(kw)
            | func.lower(Listing.location).like(kw)
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))

    # Paginate
    stmt = stmt.order_by(Listing.first_seen_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    listings = db.scalars(stmt).all()

    all_searches = db.scalars(select(SearchConfiguration).where(SearchConfiguration.deleted_at.is_(None)).order_by(SearchConfiguration.name)).all()

    return render_template(
        "listings/index.html",
        listings=listings,
        all_searches=all_searches,
        current_search_id=search_id,
        q=q,
        matched_only=matched_only,
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
