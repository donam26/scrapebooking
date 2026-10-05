import pytest

from app.channels.registry import UnsupportedUrl
from app.collector.traveloka.urls import parse_url


def test_parse_hotel_url() -> None:
    ref = parse_url(
        "https://www.traveloka.com/vi-vn/hotel/vietnam/an-lam-retreats-saigon-river-1000000393505"
        "?spec=15-10-2026.16-10-2026.1.1.HOTEL"
    )
    assert ref is not None
    assert ref.channel == "traveloka"
    assert ref.listing_key == "1000000393505"
    assert ref.external_id == "1000000393505"
    assert ref.country_code == "vn"
    assert ref.url == (
        "https://www.traveloka.com/vi-vn/hotel/vietnam/an-lam-retreats-saigon-river-1000000393505"
    )


def test_parse_english_locale_and_foreign_hotel() -> None:
    ref = parse_url("https://www.traveloka.com/en-en/hotel/malaysia/setia-sky-88-9000007840603")
    assert ref is not None
    assert ref.listing_key == "9000007840603"
    assert ref.country_code is None
    assert ref.url == "https://www.traveloka.com/vi-vn/hotel/malaysia/setia-sky-88-9000007840603"


def test_other_host_is_not_traveloka() -> None:
    assert parse_url("https://mytour.vn/khach-san/1-x.html") is None


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.traveloka.com/vi-vn/hotel",
        "https://www.traveloka.com/vi-vn/hotel/vietnam/region/phu-quoc-island-10010231",
        "https://www.traveloka.com/vi-vn/hotel/vietnam/city/da-lat-10010169",
        "https://www.traveloka.com/vi-vn/hotel/singapore/cheap-hotels-in-singapore",
    ],
)
def test_reject_non_hotel_pages(bad: str) -> None:
    with pytest.raises(UnsupportedUrl):
        parse_url(bad)
