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
_PUNCT_RE = re.compile(r"[\s\-_/|•·,.;:!?()\[\]{}*+&\"`~^<>#@%=—–…\\]+")


def normalize_text(text: str | None) -> str:
    """Normalize text into clean, single-spaced lowercase words with punctuation removed."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    s = s.lower()
    s = s.replace("'", "")       # doesn't -> doesnt, won't -> wont
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.split())


def parse_keywords(text: str | Iterable[str] | None) -> list[str]:
    """Parse newline/comma-separated keywords into unique, lowercase small-letter keywords."""
    if not text:
        return []
    items = text if not isinstance(text, str) else re.split(r"[\n,;]+", text)
    out, seen = [], set()
    for item in items:
        cleaned = str(item).strip().strip("'\"`")
        kw = " ".join(cleaned.split()).lower()
        if kw and kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


def _build_keyword_regex(normalized_kw: str) -> str:
    """Build a boundary-aware regex that allows flexible spacing between digits and letters."""
    tokens = normalized_kw.split()
    if not tokens:
        return ""
    token_patterns = []
    for token in tokens:
        p = re.escape(token)
        # Allow optional whitespace between adjacent digits and letters (e.g. 128gb -> 128\s*gb)
        p = re.sub(r"(\d)(?:\\)?([a-z])", r"\1\\s*\2", p, flags=re.IGNORECASE)
        p = re.sub(r"([a-z])(?:\\)?(\d)", r"\1\\s*\2", p, flags=re.IGNORECASE)
        token_patterns.append(p)

    pattern_parts = []
    for i, tp in enumerate(token_patterns):
        if i > 0:
            prev = tokens[i - 1]
            curr = tokens[i]
            # Transition between digit and unit/letter (e.g. "128" and "gb" or "v" and "6") allows \s*
            if (prev.isdigit() and curr.isalpha()) or (prev.isalpha() and curr.isdigit()):
                pattern_parts.append(r"\s*")
            else:
                pattern_parts.append(r"\s+")
        pattern_parts.append(tp)
    inner = "".join(pattern_parts)
    return rf"(?<![a-z0-9]){inner}(?![a-z0-9])"


def keyword_matches(haystack: str | None, keyword: str | None) -> bool:
    """Case-insensitive matching of keyword against haystack with small-letter normalization."""
    if not haystack or not keyword:
        return False
    norm_hay = normalize_text(haystack)
    norm_kw = normalize_text(keyword)
    if not norm_kw or not norm_hay:
        return False
    regex = _build_keyword_regex(norm_kw)
    if not regex:
        return False
    return re.search(regex, norm_hay, re.IGNORECASE) is not None


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
                   include_keywords=[k.lower() for k in parse_keywords(search.include_keywords)],
                   exclude_keywords=[k.lower() for k in parse_keywords(search.exclude_keywords)],
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
    mileage = listing.get("mileage") or ""
    price_str = listing.get("price_text") or ""
    url_text = listing.get("url") or ""
    # Include title, description, condition, location, seller, mileage, price, image alt, and URL text
    hay = normalize_text(" ".join([title, desc, cond, loc, seller, mileage, price_str, listing.get("image_alt") or "", url_text]))
    reasons: list[str] = []

    # 1. Exclusions always win
    for kw in c.exclude_keywords:
        if keyword_matches(hay, kw):
            return FilterResult(False, [f"excluded keyword '{kw.lower()}'"])

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
            reasons.append(f"include keyword '{hit.lower()}' found")
        else:
            missing_text = True
            reasons.append("no include keyword (checked all product info: title, desc, condition, seller, location, URL)")

    if missing_text:
        return FilterResult(False, reasons, needs_details=not desc)
    return FilterResult(True, reasons)
