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
