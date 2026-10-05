from datetime import date

import pytest

from app.channels.registry import UnsupportedUrl, parse_listing_url
from app.collector.tripcom.urls import build_detail_url, canonical_url, parse_url
from app.domain.models import ListingRef

CANONICAL = "https://vn.trip.com/hotels/detail/?hotelId=7047736"


@pytest.mark.parametrize(
    "url",
    [
        "https://vn.trip.com/hotels/detail/?hotelId=7047736",
        "https://vn.trip.com/hotels/detail/?hotelId=7047736&checkIn=2026-10-15&checkOut=2026-10-16"
        "&adult=2&crn=1&children=0&curr=VND",
        "https://www.trip.com/hotels/detail/?cityId=5649&hotelId=7047736&locale=en-XX",
        "https://vn.trip.com/hotels/v2/detail/?hotelId=7047736",
        "https://vn.trip.com/hotels/w/detail/?cityid=0&hotelid=7047736&fromShare=TripPcDetail",
        "https://www.trip.com/hotels/phu-quoc-island-hotel-detail-7047736/vinpearl-discovery-2-phu-quoc/",
        "https://us.trip.com/hotels/phu-quoc-island-hotel-detail-7047736/",
        "  https://trip.com/hotels/detail/?hotelId=7047736  ",
    ],
)
def test_parse_hotel_detail_urls(url: str) -> None:
    parsed = parse_url(url)
    assert parsed is not None
    assert parsed.channel == "tripcom"
    assert parsed.listing_key == "7047736"
    assert parsed.external_id == "7047736"
    assert parsed.url == CANONICAL


@pytest.mark.parametrize(
    "url",
    [
        "https://www.booking.com/hotel/vn/the-reverie-saigon.html",
        "https://www.tripadvisor.com/Hotel_Review-g1-d2.html",
        "https://mytrip.com/hotels/detail/?hotelId=1",
    ],
)
def test_other_hosts_are_not_tripcom(url: str) -> None:
    assert parse_url(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://vn.trip.com/hotels/",
        "https://vn.trip.com/hotels/list?city=5649&checkin=2026-10-15",
        "https://vn.trip.com/hotels/detail/?hotelId=abc",
        "https://vn.trip.com/hotels/detail/?hotelId=0",
        "https://www.trip.com/w/IsEqSkWXZW2",
        "https://vn.trip.com/flights/",
    ],
)
def test_tripcom_non_hotel_pages_are_rejected(url: str) -> None:
    with pytest.raises(UnsupportedUrl, match="Trip.com"):
        parse_url(url)


def test_registry_recognises_tripcom() -> None:
    parsed = parse_listing_url("https://vn.trip.com/hotels/detail/?hotelId=839839")
    assert parsed.channel == "tripcom"
    assert parsed.url == canonical_url("839839")


def test_build_detail_url() -> None:
    listing = ListingRef(1, "tripcom", "7047736", CANONICAL, "vn", external_id="7047736")
    url = build_detail_url(listing, date(2026, 10, 22), nights=2, adults=2, currency="VND")
    assert url == (
        "https://vn.trip.com/hotels/detail/?hotelId=7047736&checkIn=2026-10-22"
        "&checkOut=2026-10-24&adult=2&crn=1&children=0&curr=VND"
    )
