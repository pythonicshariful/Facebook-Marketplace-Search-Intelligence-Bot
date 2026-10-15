"""Classify a loaded page into an access state (pure function, unit-tested)."""
from __future__ import annotations

from enum import Enum

from bs4 import BeautifulSoup

from . import selectors as S


class PageState(str, Enum):
    OK = "ok"
    NO_RESULTS = "no_results"
    LOGIN_REQUIRED = "login_required"
    CHECKPOINT = "checkpoint"
    CAPTCHA = "captcha"
    RESTRICTED = "restricted"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    BROWSER_ERROR = "browser_error"
    UNKNOWN = "unknown"


# Require operator intervention – never retried, never re-routed to another account.
NEEDS_ATTENTION = {PageState.CHECKPOINT, PageState.CAPTCHA, PageState.RESTRICTED, PageState.RATE_LIMITED}
BLOCKING = NEEDS_ATTENTION | {PageState.LOGIN_REQUIRED}
RECOVERABLE = {PageState.NETWORK_ERROR, PageState.TIMEOUT, PageState.BROWSER_ERROR,
               PageState.UNAVAILABLE, PageState.UNKNOWN}
SUCCESS = {PageState.OK, PageState.NO_RESULTS}

DESCRIPTIONS = {
    PageState.OK: "Page loaded",
    PageState.NO_RESULTS: "Page loaded with no results",
    PageState.LOGIN_REQUIRED: "Facebook requires login for this profile",
    PageState.CHECKPOINT: "Facebook security checkpoint / identity verification",
    PageState.CAPTCHA: "Facebook presented a CAPTCHA",
    PageState.RESTRICTED: "Facebook reports the account or Marketplace access is restricted",
    PageState.RATE_LIMITED: "Facebook reports activity is too frequent (rate limited)",
    PageState.UNAVAILABLE: "Requested page is not available",
    PageState.NETWORK_ERROR: "Network error while loading page",
    PageState.TIMEOUT: "Timed out while loading page",
    PageState.BROWSER_ERROR: "Browser error",
    PageState.UNKNOWN: "Unrecognised page",
}


def _norm(text: str) -> str:
    return " ".join((text or "").replace("\u2019", "'").lower().split())


def _contains_any(text: str, phrases: list[str]) -> str | None:
    for p in phrases:
        if _norm(p) in text:
            return p
    return None


def classify(url: str, html: str, visible_text: str | None = None,
             logged_in_cookie: bool | None = None) -> tuple[PageState, str]:
    """Return (state, human detail).

    * ``visible_text`` should be the rendered body text (Selenium
      ``body.text``). If omitted it is derived from ``html`` with scripts
      removed, so that strings inside JS bundles never trigger markers.
    * ``logged_in_cookie``: True/False if known, None if unknown.
    """
    url_l = (url or "").lower()
    if url_l.startswith("chrome-error://") or "err_internet_disconnected" in (html or "").lower()[:5000]:
        return PageState.NETWORK_ERROR, DESCRIPTIONS[PageState.NETWORK_ERROR]

    soup = BeautifulSoup(html or "", "html.parser")
    if visible_text is None:
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        visible_text = soup.get_text(" ")
    text = _norm(visible_text)

    for pat in S.CHECKPOINT_URL_PATTERNS:
        if pat in url_l:
            return PageState.CHECKPOINT, f"{DESCRIPTIONS[PageState.CHECKPOINT]} (url contains '{pat}')"

    iframe_srcs = " ".join((f.get("src") or "") for f in soup.find_all("iframe")).lower()
    for marker in S.CAPTCHA_MARKERS:
        if marker in url_l or marker in iframe_srcs:
            return PageState.CAPTCHA, DESCRIPTIONS[PageState.CAPTCHA]

    hit = _contains_any(text, S.RESTRICTION_TEXT)
    if hit:
        return PageState.RESTRICTED, f"{DESCRIPTIONS[PageState.RESTRICTED]}: \"{hit}\""
    hit = _contains_any(text, S.RATE_LIMIT_TEXT)
    if hit:
        return PageState.RATE_LIMITED, f"{DESCRIPTIONS[PageState.RATE_LIMITED]}: \"{hit}\""

    has_login_form = bool(soup.select_one('input[name="email"]')) and bool(soup.select_one('input[name="pass"]'))
    login_url = any(p in url_l for p in S.LOGIN_URL_PATTERNS)
    if login_url or (has_login_form and logged_in_cookie is not True) or logged_in_cookie is False:
        return PageState.LOGIN_REQUIRED, DESCRIPTIONS[PageState.LOGIN_REQUIRED]

    hit = _contains_any(text, S.CHECKPOINT_TEXT)
    if hit and not soup.select_one(S.LISTING_LINK_CSS):
        return PageState.CHECKPOINT, f"{DESCRIPTIONS[PageState.CHECKPOINT]}: \"{hit}\""

    if soup.select_one(S.LISTING_LINK_CSS):
        return PageState.OK, DESCRIPTIONS[PageState.OK]

    hit = _contains_any(text, S.UNAVAILABLE_TEXT)
    if hit:
        return PageState.UNAVAILABLE, f"{DESCRIPTIONS[PageState.UNAVAILABLE]}: \"{hit}\""
    if _contains_any(text, S.NO_RESULTS_TEXT):
        return PageState.NO_RESULTS, DESCRIPTIONS[PageState.NO_RESULTS]
    if "facebook.com" in url_l and text:
        # Logged in, page rendered but no listing links (could be empty results
        # or changed markup). Treated as success with zero results; the
        # dashboard surfaces repeated zero-result runs.
        return PageState.NO_RESULTS, "Page loaded but no listing links were found (empty results or changed markup)"
    return PageState.UNKNOWN, DESCRIPTIONS[PageState.UNKNOWN]
