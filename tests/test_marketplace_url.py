import pytest
from app.models import SearchConfiguration
from app.services.marketplace_url import build_search_url


def test_build_search_url():
    search = SearchConfiguration(
        name="Civic",
        search_terms="Honda Civic",
        location_slug="portland",
        min_price=500,
        max_price=2000,
        sort_by="newest",
        radius_miles=25,
    )
    url = build_search_url(search)
    assert "facebook.com/marketplace/portland/search/" in url
    assert "query=Honda%20Civic" in url
    assert "minPrice=500" in url
    assert "maxPrice=2000" in url
    assert "sortBy=creation_time_descend" in url
    assert "radius=40" in url  # 25 mi * 1.609344 ≈ 40 km
