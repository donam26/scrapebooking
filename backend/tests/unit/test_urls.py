from datetime import date

from app.collector.booking.urls import build_hotel_url, currency_for
from app.domain.models import HotelRef

HOTEL = HotelRef(
    id=1,
    country_code="vn",
    slug="vn/the-reverie-saigon",
    canonical_url="https://www.booking.com/hotel/vn/the-reverie-saigon.html",
)


def test_build_hotel_url() -> None:
    url = build_hotel_url(HOTEL, checkin=date(2026, 10, 5), nights=2, adults=2, currency="VND")
    assert url == (
        "https://www.booking.com/hotel/vn/the-reverie-saigon.en-gb.html"
        "?checkin=2026-10-05&checkout=2026-10-07&group_adults=2&no_rooms=1"
        "&group_children=0&selected_currency=VND&lang=en-gb"
    )


def test_currency_for_known_and_default() -> None:
    assert currency_for("vn") == "VND"
    assert currency_for("th") == "THB"
    assert currency_for("zz") == "USD"
