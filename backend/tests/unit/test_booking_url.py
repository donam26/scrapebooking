import pytest

from app.domain.booking_url import BookingUrlError, parse_booking_url


def test_parse_standard_url() -> None:
    ref = parse_booking_url("https://www.booking.com/hotel/vn/the-reverie-saigon.html?aid=1&x=2")
    assert ref.country_code == "vn"
    assert ref.slug == "vn/the-reverie-saigon"
    assert ref.pagename == "the-reverie-saigon"
    assert ref.canonical_url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"


def test_parse_localized_domain_and_lang_suffix() -> None:
    ref = parse_booking_url("https://www.booking.com/hotel/vn/the-reverie-saigon.vi.html")
    assert ref.slug == "vn/the-reverie-saigon"
    assert ref.canonical_url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.booking.com/searchresults.html?ss=hanoi",
        "https://example.com/hotel/vn/x.html",
        "not a url",
    ],
)
def test_reject_non_hotel_urls(bad: str) -> None:
    with pytest.raises(BookingUrlError):
        parse_booking_url(bad)
