import pytest

from app.channels.registry import UnsupportedUrl
from app.collector.expedia.urls import parse_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.expedia.com/Ho-Chi-Minh-City-Hotels-Rex-Hotel-Saigon.h481670.Hotel-Information",
        "https://www.expedia.com.vn/Ho-Chi-Minh-City-Khach-San-Rex-Hotel.h481670.Thong-tin-khach-san"
        "?chkin=2026-10-13&chkout=2026-10-14&rm1=a2",
        "https://www.expedia.co.uk/Ho-Chi-Minh-City-Hotels-Rex-Hotel-Saigon.h481670.Hotel-Information",
    ],
)
def test_parse_hotel_url_on_any_country_domain(url: str) -> None:
    ref = parse_url(url)
    assert ref is not None
    assert ref.channel == "expedia"
    assert ref.listing_key == "481670"
    assert ref.external_id == "481670"
    assert ref.url.startswith("https://www.expedia.com.vn/")
    assert ref.url.endswith(".h481670.Hotel-Information")


@pytest.mark.parametrize(
    "other",
    [
        "https://www.booking.com/hotel/vn/x.html",
        "https://expedia.com.evil.io/x.h1.Hotel-Information",
    ],
)
def test_other_hosts_are_not_expedia(other: str) -> None:
    assert parse_url(other) is None


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.expedia.com.vn/",
        "https://www.expedia.com/Ho-Chi-Minh-City-Hotels.d6046931.Travel-Guide-Hotels",
    ],
)
def test_reject_non_hotel_pages(bad: str) -> None:
    with pytest.raises(UnsupportedUrl):
        parse_url(bad)
