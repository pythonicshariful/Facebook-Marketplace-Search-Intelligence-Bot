"""Normalization and application-side filtering of listings."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

# Built-in condition keyword groups (applied app-side; Marketplace has no
# native "blown engine" filter). Matched on title + description (if fetched).
CONDITION_KEYWORDS: dict[str, tuple[str, list[str]]] = {
    "any": ("Any condition", []),
    "damaged": ("Damaged / wrecked", ["damaged", "damage", "wrecked", "wreck", "accident", "collision",
                                     "hail damage", "flood", "front end damage", "rear ended"]),
    "blown_engine": ("Blown / bad engine", ["blown engine", "engine blown", "blown motor", "bad engine",
                                           "bad motor", "engine knock", "rod knock", "knocking", "seized",
                                           "needs engine", "needs motor", "no engine", "spun bearing",
                                           "head gasket", "overheated", "threw a rod", "engine problems"]),
    "non_running": ("Not running", ["not running", "non running", "doesn't run", "does not run",
                                   "doesnt run", "won't start", "wont start", "will not start", "no start",
                                   "needs tow", "runs bad", "dead", "not driveable", "not drivable"]),
    "salvage": ("Salvage / rebuilt title", ["salvage", "salvaged", "rebuilt title", "branded title",
                                           "total loss", "totaled", "parts car"]),
    "repairable": ("Repairable / needs work", ["needs repair", "needs work", "mechanic special", "project car",
                                              "project", "fixer", "fixer upper", "as is", "repairable",
                                              "needs tlc", "handyman special"]),
    "any_problem": ("Any problem vehicle (all of the above)", []),
}
CONDITION_KEYWORDS["any_problem"] = (
    CONDITION_KEYWORDS["any_problem"][0],
    sorted({kw for k, (_, kws) in CONDITION_KEYWORDS.items() if k not in ("any", "any_problem") for kw in kws}),
)

_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    s = s.lower()
    s = re.sub(r"[-_/|•·,.;:!?()\[\]{}]+", " ", s)
    s = s.replace("'", "")       # doesn't -> doesnt, won't -> wont
    return " ".join(s.split())


def parse_keywords(text: str | Iterable[str] | None) -> list[str]:
    if not text:
        return []
    items = text if not isinstance(text, str) else re.split(r"[\n,;]+", text)
    out, seen = [], set()
    for item in items:
        kw = " ".join(str(item).split())
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            out.append(kw)
    return out


def keyword_matches(norm_haystack: str, keyword: str) -> bool:
    kw = normalize_text(keyword)
    if not kw:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", norm_haystack) is not None


_PRICE_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?")


def parse_price_cents(text: str | None) -> int | None:
    """'$1,500' -> 150000, 'Free' -> 0, '$2.5K' -> 250000, unknown -> None."""
    if not text:
        return None
    t = text.strip()
    if t.lower() in {"free", "$0"}:
        return 0
    m = _PRICE_NUM_RE.search(t)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(round(value * mult * 100))


@dataclass
class SearchCriteria:
    make: str | None = None
    model: str | None = None
    min_price: int | None = None   # dollars
    max_price: int | None = None
    vehicle_condition: str = "any"
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    accept_unknown_price: bool = True

    @classmethod
    def from_search(cls, search, accept_unknown_price: bool = True) -> "SearchCriteria":
        return cls(make=search.make, model=search.model, min_price=search.min_price,
                   max_price=search.max_price, vehicle_condition=search.vehicle_condition or "any",
                   include_keywords=parse_keywords(search.include_keywords),
                   exclude_keywords=parse_keywords(search.exclude_keywords),
                   accept_unknown_price=accept_unknown_price)

    @property
    def needs_text_match(self) -> bool:
        return bool(self.include_keywords) or self.vehicle_condition not in ("any", "", None)


@dataclass
class FilterResult:
    matched: bool
    reasons: list[str]
    needs_details: bool = False   # would match if description were known

    @property
    def summary(self) -> str:
        return "; ".join(self.reasons)


def evaluate(listing: dict[str, Any], c: SearchCriteria) -> FilterResult:
    title = listing.get("title") or ""
    desc = listing.get("description") or ""
    cond = listing.get("condition") or ""
    loc = listing.get("location") or ""
    seller = listing.get("seller_name") or ""
    # Include title, description, condition, location, seller, image alt, and URL text
    url_text = listing.get("url") or ""
    hay = normalize_text(" ".join([title, desc, cond, loc, seller, listing.get("image_alt") or "", url_text]))
    reasons: list[str] = []

    # 1. Exclusions always win
    for kw in c.exclude_keywords:
        if keyword_matches(hay, kw):
            return FilterResult(False, [f"excluded keyword '{kw}'"])

    # 2. Price bounds
    price = listing.get("price_cents")
    if price is None:
        if (c.min_price is not None or c.max_price is not None) and not c.accept_unknown_price:
            return FilterResult(False, ["price unknown"])
        reasons.append("price unknown")
    else:
        if c.min_price is not None and price < c.min_price * 100:
            return FilterResult(False, [f"price ${price/100:,.0f} below min ${c.min_price:,}"])
        if c.max_price is not None and price > c.max_price * 100:
            return FilterResult(False, [f"price ${price/100:,.0f} above max ${c.max_price:,}"])
        reasons.append(f"price ${price/100:,.0f} in range")

    # 3. Make / model must appear in title (or description)
    for label, value in (("make", c.make), ("model", c.model)):
        if value and not keyword_matches(hay, value):
            return FilterResult(False, [f"{label} '{value}' not in title"])
        if value:
            reasons.append(f"{label} '{value}' found")

    # 4. Condition keywords + include keywords (both must be satisfied if set)
    missing_text = False
    if c.vehicle_condition not in ("any", "", None):
        kws = CONDITION_KEYWORDS.get(c.vehicle_condition, ("", []))[1]
        hit = next((k for k in kws if keyword_matches(hay, k)), None)
        if hit:
            reasons.append(f"condition keyword '{hit}'")
        else:
            missing_text = True
            reasons.append(f"no '{c.vehicle_condition}' condition keyword")
    if c.include_keywords:
        hit = next((k for k in c.include_keywords if keyword_matches(hay, k)), None)
        if hit:
            reasons.append(f"include keyword '{hit}' found")
        else:
            missing_text = True
            reasons.append("no include keyword (checked all product info: title, desc, condition, seller, location, URL)")

    if missing_text:
        return FilterResult(False, reasons, needs_details=not desc)
    return FilterResult(True, reasons)
