"""Facebook Marketplace page selectors and page-state markers.

ALL website-specific selectors live in this module. When Facebook changes its
markup, update this file only, then run ``pytest tests/test_extractor.py``
and a manual search on a logged-in profile.  See docs/SELECTORS.md.

Design principles
-----------------
* Avoid obfuscated CSS class names (e.g. ``x1lliihq``) – they change often.
* Anchor on stable semantics: listing links always contain
  ``/marketplace/item/<numeric id>``; login forms use ``name="email"`` /
  ``name="pass"``; checkpoints use ``/checkpoint`` URLs.
* Text markers are matched case-insensitively on normalized visible text.
  They are English; add translations if the profile uses another language.
"""
from __future__ import annotations

import re

# --- Listings -------------------------------------------------------------
LISTING_LINK_CSS = 'a[href*="/marketplace/item/"]'
ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")
# Elements whose presence means the search results grid has rendered.
RESULTS_READY_CSS = [LISTING_LINK_CSS, 'div[role="main"]']

# Listing detail page
DETAIL_META = {
    "title": 'meta[property="og:title"]',
    "description": 'meta[property="og:description"]',
    "image": 'meta[property="og:image"]',
}

# Text-line heuristics inside a listing card
PRICE_LINE_RE = re.compile(r"^(?:[A-Z]{0,3}\$|US\$|CA\$|£|€|₹|৳)\s?[\d.,]+\s?[KkMm]?$|^free$", re.I)
MILEAGE_LINE_RE = re.compile(r"\b\d[\d.,]*\s?[Kk]?\s?(?:miles|mi|km)\b", re.I)
LOCATION_LINE_RE = re.compile(r"^[A-Za-z .'\-]+,\s?[A-Z]{2}$|^[A-Za-z .'\-]+,\s?[A-Za-z .'\-]+$")

# --- Login / access state --------------------------------------------------
LOGGED_IN_COOKIE = "c_user"     # presence only is checked, value never read/logged
LOGIN_FORM_CSS = ['input[name="email"]', 'input[name="pass"]', "form#login_form",
                  'form[action*="/login"]']
LOGIN_URL_PATTERNS = ["/login", "login.php", "/r.php"]
CHECKPOINT_URL_PATTERNS = ["/checkpoint", "two_step_verification", "/auth_platform",
                           "/confirmemail", "/recover"]
CAPTCHA_MARKERS = ["captcha", "recaptcha", "arkoselabs", "funcaptcha", "hcaptcha"]

RESTRICTION_TEXT = [
    "you're temporarily blocked",
    "you’re temporarily blocked",
    "temporarily restricted",
    "your account has been locked",
    "your account has been suspended",
    "your account is restricted",
    "you can't use marketplace",
    "you can’t use marketplace",
    "marketplace isn't available to you",
    "marketplace isn’t available to you",
    "you've been restricted",
    "we suspended your account",
]
RATE_LIMIT_TEXT = [
    "you're going too fast",
    "you’re going too fast",
    "we limit how often",
    "it looks like you were misusing this feature",
]
UNAVAILABLE_TEXT = [
    "this content isn't available",
    "this content isn’t available",
    "this page isn't available",
    "this page isn’t available",
    "this listing is no longer available",
]
CHECKPOINT_TEXT = [
    "confirm your identity",
    "security check",
    "enter the code",
    "approve your login",
    "we noticed unusual activity",
    "secure your account",
]
NO_RESULTS_TEXT = ["no listings found", "we didn't find anything", "we didn’t find anything",
                   "no results"]
