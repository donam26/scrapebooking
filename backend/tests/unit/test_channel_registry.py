"""Danh mục kênh: nhận diện URL listing (thay cho app/domain/booking_url.py cũ)."""

import pytest

from app.channels.registry import (
    ChannelCode,
    UnsupportedUrl,
    channel_name,
    channels,
    parse_listing_url,
    sort_channels,
)


def test_parse_booking_standard_url() -> None:
    ref = parse_listing_url("https://www.booking.com/hotel/vn/the-reverie-saigon.html?aid=1&x=2")
    assert ref.channel == "booking"
    assert ref.listing_key == "vn/the-reverie-saigon"
    assert ref.country_code == "vn"
    assert ref.url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"
    assert ref.external_id is None


def test_parse_booking_localized_suffix_and_subdomain() -> None:
    ref = parse_listing_url("  https://m.booking.com/hotel/vn/the-reverie-saigon.vi.html  ")
    assert ref.listing_key == "vn/the-reverie-saigon"
    assert ref.url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.booking.com/searchresults.html?ss=hanoi",
        "https://www.booking.com/hotel/vn/",
    ],
)
def test_booking_non_hotel_path_is_rejected_with_booking_hint(bad: str) -> None:
    with pytest.raises(UnsupportedUrl, match="booking.com/hotel/vn/ten-khach-san.html"):
        parse_listing_url(bad)


def test_lookalike_host_is_not_booking() -> None:
    with pytest.raises(UnsupportedUrl, match="Chưa hỗ trợ trang này"):
        parse_listing_url("https://notbooking.com/hotel/vn/x.html")


@pytest.mark.parametrize("bad", ["https://example.com/hotel/vn/x.html", "https://foo.vn/abc"])
def test_unsupported_host_lists_supported_channels(bad: str) -> None:
    with pytest.raises(UnsupportedUrl, match="Booking.com") as exc:
        parse_listing_url(bad)
    assert "Chưa hỗ trợ trang này" in str(exc.value)


@pytest.mark.parametrize("bad", ["not a url", "www.booking.com/hotel/vn/x.html", "ftp://x/y"])
def test_malformed_url(bad: str) -> None:
    with pytest.raises(UnsupportedUrl, match="https://"):
        parse_listing_url(bad)


def test_booking_is_registered_and_collectable() -> None:
    info = channels()[ChannelCode.BOOKING]
    assert info.collectable and info.name == "Booking.com"
    assert channel_name("booking") == "Booking.com"
    assert channel_name("nowhere") == "nowhere"


def test_sort_channels_by_market_order_unknown_last() -> None:
    assert sort_channels(["zz", "agoda", "booking", "agoda", "ivivu"]) == [
        "booking",
        "agoda",
        "ivivu",
        "zz",
    ]
