import pytest
from app.services.extractor import extract_listings, canonical_item_url
from tests.fixtures import MARKETPLACE_RESULTS_HTML


def test_canonical_url():
    assert canonical_item_url("/marketplace/item/123456789/?ref=search") == "https://www.facebook.com/marketplace/item/123456789/"
    assert canonical_item_url("https://www.facebook.com/marketplace/item/987654321/") == "https://www.facebook.com/marketplace/item/987654321/"


def test_extract_listings_from_html():
    listings = extract_listings(MARKETPLACE_RESULTS_HTML)
    assert len(listings) == 3

    # Check listing 1
    c1 = listings[0]
    assert c1["fb_item_id"] == "1029384756"
    assert c1["price_text"] == "$1,400"
    assert c1["price_cents"] == 140000
    assert "2012 Honda Civic" in c1["title"]
    assert c1["location"] == "Portland, OR"
    assert c1["mileage"] == "145K miles"

    # Check listing 2
    c2 = listings[1]
    assert c2["fb_item_id"] == "5566778899"
    assert c2["price_cents"] == 80000
    assert "Blown engine" in c2["title"]
