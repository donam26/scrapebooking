import base64
import json
from datetime import date

import pytest

from app.channels.registry import UnsupportedUrl, parse_listing_url
from app.collector.agoda.urls import (
    canonical_url,
    gate_meta,
    parse_url,
    property_id,
    room_grid_request,
    secondary_data_url,
    suggest_url,
)
from app.domain.models import ListingRef

MELIA_KEY = "melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.agoda.com/vi-vn/melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn.html",
        "https://www.agoda.com/melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn.html",
        "https://www.agoda.com/en-gb/melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn.html"
        "?checkIn=2026-10-15&los=1&rooms=1&adults=2&children=0&currencyCode=VND#rooms",
        "  https://agoda.com/vi-vn/Melia-Vinpearl-Phu-Quoc/hotel/phu-quoc-island-vn.html  ",
    ],
)
def test_hotel_page_any_locale_gives_same_key(url: str) -> None:
    listing = parse_url(url)
    assert listing is not None
    assert listing.channel == "agoda"
    assert listing.listing_key == MELIA_KEY
    assert listing.url == f"https://www.agoda.com/vi-vn/{MELIA_KEY}.html"
    assert listing.country_code == "vn"
    assert listing.external_id is None


def test_slug_with_underscore_and_digits() -> None:
    listing = parse_url(
        "https://www.agoda.com/vi-vn/vinpearl-discovery-2-phu-quoc_2/hotel/phu-quoc-island-vn.html"
    )
    assert listing is not None
    assert listing.listing_key == "vinpearl-discovery-2-phu-quoc_2/hotel/phu-quoc-island-vn"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.agoda.com/vi-vn/search?selectedproperty=10971&city=13170",
        "https://www.agoda.com/search?hotel=10971&selectedproperty=10971&asq=abc",
        "https://www.agoda.com/partners/partnersearch.aspx?hid=10971",
    ],
)
def test_property_id_only_urls(url: str) -> None:
    listing = parse_url(url)
    assert listing is not None
    assert listing.listing_key == "id/10971"
    assert listing.external_id == "10971"
    assert listing.url == "https://www.agoda.com/vi-vn/search?selectedproperty=10971"


def test_hotel_page_keeps_property_id_from_query() -> None:
    listing = parse_url(
        "https://www.agoda.com/vi-vn/caravelle-saigon-hotel/hotel/ho-chi-minh-city-vn.html"
        "?selectedProperty=10971"
    )
    assert listing is not None
    assert listing.listing_key == "caravelle-saigon-hotel/hotel/ho-chi-minh-city-vn"
    assert listing.external_id == "10971"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.agoda.com/vi-vn/",
        "https://www.agoda.com/vi-vn/city/phu-quoc-island-vn.html",
        "https://www.agoda.com/vi-vn/search?city=17188",
    ],
)
def test_agoda_non_hotel_page_rejected_in_vietnamese(url: str) -> None:
    with pytest.raises(UnsupportedUrl, match="trang của một khách sạn"):
        parse_url(url)


def test_other_hosts_are_not_agoda() -> None:
    assert parse_url("https://www.booking.com/hotel/vn/x.html") is None
    assert parse_url("https://notagoda.com/vi-vn/x/hotel/y-vn.html") is None


def test_registry_routes_agoda_urls() -> None:
    listing = parse_listing_url(
        "https://www.agoda.com/vi-vn/melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn.html"
    )
    assert (listing.channel, listing.listing_key) == ("agoda", MELIA_KEY)


def _ref(key: str, external_id: str | None = None) -> ListingRef:
    return ListingRef(1, "agoda", key, canonical_url(key), "vn", external_id)


def test_property_id_from_ref() -> None:
    assert property_id(_ref(MELIA_KEY)) is None
    assert property_id(_ref(MELIA_KEY, "1985199")) == "1985199"
    assert property_id(_ref("id/10971")) == "10971"


def test_secondary_data_url_with_and_without_dates() -> None:
    url = secondary_data_url("1985199", date(2026, 10, 20), 2, 2, "VND")
    assert url.startswith(
        "https://www.agoda.com/api/cronos/property/BelowFoldParams/GetSecondaryData?"
    )
    assert "checkIn=2026-10-20&los=2&rooms=1&adults=2&children=0&currencyCode=VND" in url
    assert "hotel_id=1985199" in url and "price_view=2" in url
    dateless = secondary_data_url("10971")
    assert "checkIn" not in dateless and "hotel_id=10971" in dateless


def test_suggest_url_encodes_text() -> None:
    url = suggest_url("Melia Vinpearl Phú Quốc")
    assert "/GetUnifiedSuggestResult/3/24/24/0/vi-vn/" in url
    assert "searchText=Melia%20Vinpearl%20Ph%C3%BA%20Qu%E1%BB%91c" in url
    assert "origin=VN" in url


def test_room_grid_request_and_gate_header() -> None:
    payload = room_grid_request("3647146", date(2026, 10, 3), 2, 2, "VND")
    assert payload["propertyId"] == "3647146"
    assert payload["searchCriteria"]["checkIn"] == "2026-10-03"
    assert payload["searchCriteria"]["checkOut"] == "2026-10-05"
    assert payload["userContext"]["currencyId"] == 78
    json.dumps(payload)  # gửi được dạng JSON
    decoded = base64.b64decode(gate_meta(1790841166112, "user-1")).decode()
    assert decoded == "1790841166112|user-1|/api/v1/property/room-grid"
