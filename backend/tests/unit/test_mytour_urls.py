import pytest

from app.channels.registry import UnsupportedUrl
from app.collector.mytour.urls import canonical_url, parse_url


def test_parse_hotel_url_with_search_params() -> None:
    ref = parse_url(
        "https://mytour.vn/khach-san/23812-sol-by-melia-phu-quoc.html"
        "?checkIn=15-10-2026&checkOut=16-10-2026&adults=2&rooms=1&children=0"
    )
    assert ref is not None
    assert ref.channel == "mytour"
    assert ref.listing_key == "23812"
    assert ref.external_id == "23812"
    assert ref.url == "https://mytour.vn/khach-san/23812-sol-by-melia-phu-quoc.html"


def test_other_host_is_not_mytour() -> None:
    assert parse_url("https://www.booking.com/hotel/vn/x.html") is None


@pytest.mark.parametrize(
    "bad",
    [
        "https://mytour.vn/",
        "https://mytour.vn/khach-san/td446/khach-san-tai-phu-quoc.html",
        "https://mytour.vn/khach-san/khach-san-gia-tot/tp2/khach-san-tai-kien-giang.html",
    ],
)
def test_reject_non_hotel_pages(bad: str) -> None:
    with pytest.raises(UnsupportedUrl):
        parse_url(bad)


def test_canonical_url_strips_api_slug_suffix() -> None:
    assert (
        canonical_url(23812, "sol-by-melia-phu-quoc-h23812")
        == "https://mytour.vn/khach-san/23812-sol-by-melia-phu-quoc.html"
    )
