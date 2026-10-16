import pytest
from app.services.filtering import (
    SearchCriteria,
    evaluate,
    normalize_text,
    parse_price_cents,
)


def test_normalize_text():
    assert normalize_text("HONDA CIVIC - Damaged!") == "honda civic damaged"
    assert normalize_text("Doesn't run, won't start") == "doesnt run wont start"


def test_parse_price_cents():
    assert parse_price_cents("$1,500") == 150000
    assert parse_price_cents("Free") == 0
    assert parse_price_cents("$0") == 0
    assert parse_price_cents("$2.5K") == 250000
    assert parse_price_cents("Contact Seller") is None


def test_evaluate_filter_matching():
    criteria = SearchCriteria(
        make="Honda",
        model="Civic",
        min_price=500,
        max_price=2000,
        vehicle_condition="damaged",
        include_keywords=["damaged", "blown engine", "non-running"],
        exclude_keywords=["parts only", "accessories"],
    )

    # 1. Matching candidate
    match_candidate = {
        "title": "2010 Honda Civic LX - Damaged front bumper",
        "price_cents": 120000,
        "description": "Runs good, clear title, needs fender and headlight.",
    }
    res = evaluate(match_candidate, criteria)
    assert res.matched is True
    assert "price $1,200 in range" in res.summary

    # 2. Excluded keyword candidate
    excluded_candidate = {
        "title": "Honda Civic parts only - parting out damaged car",
        "price_cents": 60000,
    }
    res_ex = evaluate(excluded_candidate, criteria)
    assert res_ex.matched is False
    assert "excluded keyword 'parts only'" in res_ex.summary

    # 3. Out of price range candidate
    expensive_candidate = {
        "title": "2015 Honda Civic - Damaged door",
        "price_cents": 450000,  # $4,500
    }
    res_price = evaluate(expensive_candidate, criteria)
    assert res_price.matched is False
    assert "above max $2,000" in res_price.summary


def test_include_keywords_case_insensitivity_and_small_letter():
    from app.services.filtering import parse_keywords, keyword_matches

    # 1. parse_keywords converts to small letters and strips quotes/spaces
    raw = "128GB\nDAMAGED\n'Unlocked'\n  Clean Title  \n128gb"
    parsed = parse_keywords(raw)
    assert parsed == ["128gb", "damaged", "unlocked", "clean title"]

    # 2. Case-insensitive matching with mixed case haystack and keyword
    assert keyword_matches("iPhone 12 - 128GB Damaged!", "128gb") is True
    assert keyword_matches("iPhone 12 - 128gb", "128GB") is True
    assert keyword_matches("iPhone 12 - 128 GB (Clean)", "128gb") is True
    assert keyword_matches("iPhone 12 - 128GB", "128 gb") is True
    assert keyword_matches("Apple iPhone 12 Pro (Unlocked)", "UNLOCKED") is True
    assert keyword_matches('Apple iPhone 12 "Damaged" + Charger', "damaged") is True

    # 3. False positives check (word boundaries)
    assert keyword_matches("Undamaged phone in mint condition", "damaged") is False
    assert keyword_matches("Carpet cleaner", "car") is False

    # 4. Evaluation with uppercase criteria matches and outputs small letter
    criteria = SearchCriteria(
        include_keywords=["128GB", "UNLOCKED"],
    )
    listing = {
        "title": "Apple iPhone 11 (128 gb) - Factory Unlocked",
        "price_cents": 25000,
    }
    res = evaluate(listing, criteria)
    assert res.matched is True
    assert "include keyword '128gb' found" in res.summary

