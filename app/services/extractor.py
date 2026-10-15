"""Extract listing data from Marketplace HTML (works on Selenium page_source
or on saved fixture files – no browser needed for tests)."""
from __future__ import annotations

import html as html_lib
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from . import selectors as S
from .filtering import parse_price_cents

FB_ORIGIN = "https://www.facebook.com"


def canonical_item_url(href: str) -> str:
    absolute = urljoin(FB_ORIGIN, href)
    parts = urlsplit(absolute)
    m = S.ITEM_ID_RE.search(parts.path)
    if m:
        return f"{FB_ORIGIN}/marketplace/item/{m.group(1)}/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, "", ""))


def _lines(tag: Tag) -> list[str]:
    out: list[str] = []
    for s in tag.stripped_strings:
        s = " ".join(html_lib.unescape(s).split())
        if s and (not out or out[-1] != s):
            out.append(s)
    return out


def parse_card(anchor: Tag) -> dict[str, Any] | None:
    href = anchor.get("href") or ""
    m = S.ITEM_ID_RE.search(href)
    url = canonical_item_url(href)
    lines = _lines(anchor)
    img = anchor.find("img")
    img_alt = (img.get("alt") or "").strip() if img else ""
    img_src = (img.get("src") or "").strip() if img else ""

    price_text = None
    title = None
    location = None
    mileage = None
    rest: list[str] = []
    for line in lines:
        if price_text is None and S.PRICE_LINE_RE.match(line):
            price_text = line
            continue
        if S.PRICE_LINE_RE.match(line):
            continue  # struck-through original price
        if mileage is None and S.MILEAGE_LINE_RE.search(line) and len(line) < 30:
            mileage = line
            continue
        rest.append(line)
    if rest:
        title = rest[0]
    for line in rest[1:]:
        if S.LOCATION_LINE_RE.match(line):
            location = line
            break
    # Fallback to aria-label if fields missing (Facebook exposes: title, price, location, listing id)
    aria_label = (anchor.get("aria-label") or "").strip()
    if aria_label and (not title or not price_text or not location):
        parts = [p.strip() for p in aria_label.split(",") if p.strip()]
        if not title and parts:
            title = parts[0]
        for p in parts:
            if not price_text and S.PRICE_LINE_RE.match(p):
                price_text = p
            elif not location and S.LOCATION_LINE_RE.match(p):
                location = p

    if not title and img_alt:
        title = img_alt
    if not title and not m:
        return None
    return {
        "fb_item_id": m.group(1) if m else None,
        "url": url,
        "title": (title or "").strip()[:300],
        "price_text": price_text,
        "price_cents": parse_price_cents(price_text) if price_text else None,
        "location": location,
        "mileage": mileage,
        "condition": None,
        "description": None,
        "seller_name": None,
        "posted_text": None,
        "image_url": img_src[:1000] or None,
        "image_alt": img_alt or None,
    }


def extract_listings(page_html: str) -> list[dict[str, Any]]:
    """Return de-duplicated listing dicts in page order."""
    soup = BeautifulSoup(page_html or "", "html.parser")
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for a in soup.select(S.LISTING_LINK_CSS):
        card = parse_card(a)
        if not card:
            continue
        key = card["fb_item_id"] or card["url"]
        if key in seen:
            continue
        seen.add(key)
        results.append(card)
    return results


def extract_detail(page_html: str) -> dict[str, Any]:
    """Best-effort details from a listing page (Open Graph meta tags)."""
    soup = BeautifulSoup(page_html or "", "html.parser")
    out: dict[str, Any] = {}
    for key, css in S.DETAIL_META.items():
        tag = soup.select_one(css)
        if tag and tag.get("content"):
            out[key] = " ".join(html_lib.unescape(tag["content"]).split())
    return out
