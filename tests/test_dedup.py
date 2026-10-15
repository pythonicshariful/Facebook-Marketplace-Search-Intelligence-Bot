import pytest
from app.services.dedup import listing_key, notification_key


def test_listing_key_stable_id():
    raw_with_id = {"fb_item_id": "123456789", "url": "https://www.facebook.com/marketplace/item/123456789/"}
    key, key_type = listing_key(raw_with_id)
    assert key == "fb:123456789"
    assert key_type == "fb_id"


def test_listing_key_fingerprint_fallback():
    raw_without_id = {
        "url": "https://www.facebook.com/marketplace/item/something/",
        "title": "2010 Civic Damaged",
        "price_cents": 150000,
        "location": "Portland, OR",
    }
    key, key_type = listing_key(raw_without_id)
    assert key.startswith("fp:")
    assert key_type == "fingerprint"
    assert len(key) == 35  # "fp:" + 32 chars


def test_notification_dedup_keys():
    # Global scope
    k_global = notification_key(listing_id=42, search_id=1, scope="global")
    assert k_global == "new:42"

    # Per search scope
    k_search = notification_key(listing_id=42, search_id=1, scope="per_search")
    assert k_search == "new:42:s1"

    # Price drop
    k_drop = notification_key(listing_id=42, search_id=1, scope="global", kind="price_drop", price_cents=80000)
    assert k_drop == "drop:42:s1:80000"
