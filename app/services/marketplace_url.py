"""Build Facebook Marketplace search URLs.

Only parameters observed in real Marketplace search URLs are encoded.
Everything else (make/model strictness, vehicle condition, keywords) is
applied application-side in ``filtering.py``.

Parameter status (re-verify in the target environment, see docs/SELECTORS.md):

=================  =========================================  =============
Parameter          Meaning                                    Status
=================  =========================================  =============
path location      /marketplace/<slug-or-numeric-id>/search   observed
query              free-text search                           observed
minPrice/maxPrice  whole currency units                       observed
sortBy             creation_time_descend, price_ascend, ...   observed
exact              false = fuzzy matching                     observed
radius             kilometres (FB uses km internally)         UNVERIFIED –
                                                              FB may ignore
                                                              it and use the
                                                              profile's saved
                                                              radius
=================  =========================================  =============

ZIP codes cannot be put directly in the URL. Use a location slug (e.g.
``portland``) or the numeric location id visible in the URL after choosing
the location manually in the browser. If no slug is set, Facebook uses the
location saved in that browser profile.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlencode

BASE = "https://www.facebook.com/marketplace"

SORT_OPTIONS: dict[str, tuple[str, str | None]] = {
    "newest": ("Date listed: newest first", "creation_time_descend"),
    "best_match": ("Best match (Facebook default)", None),
    "price_asc": ("Price: lowest first", "price_ascend"),
    "price_desc": ("Price: highest first", "price_descend"),
    "distance": ("Distance: nearest first", "distance_ascend"),
}

_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]{2,80}$")
MILES_TO_KM = 1.609344


def valid_slug(slug: str | None) -> bool:
    return not slug or bool(_SLUG_RE.match(slug))


def build_query(search_terms: str, make: str | None, model: str | None) -> str:
    words: list[str] = []
    seen: set[str] = set()
    for part in (search_terms or "", make or "", model or ""):
        for w in part.split():
            if w.lower() not in seen:
                seen.add(w.lower())
                words.append(w)
    return " ".join(words)


def build_search_url(search) -> str:
    slug = (search.location_slug or "").strip()
    if slug and not valid_slug(slug):
        raise ValueError("Invalid location slug")
    path = f"{BASE}/{quote(slug)}/search/" if slug else f"{BASE}/search/"
    params: dict[str, str] = {}
    query = build_query(search.search_terms, search.make, search.model)
    if not query:
        raise ValueError("Search needs search terms or a make/model")
    params["query"] = query
    if search.min_price is not None:
        params["minPrice"] = str(int(search.min_price))
    if search.max_price is not None:
        params["maxPrice"] = str(int(search.max_price))
    sort_param = SORT_OPTIONS.get(search.sort_by or "newest", (None, None))[1]
    if sort_param:
        params["sortBy"] = sort_param
    if search.radius_miles:
        params["radius"] = str(max(1, round(search.radius_miles * MILES_TO_KM)))
    params["exact"] = "false"
    return f"{path}?{urlencode(params, quote_via=quote)}"
