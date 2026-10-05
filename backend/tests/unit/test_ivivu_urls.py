import pytest

from app.channels.registry import UnsupportedUrl
from app.collector.ivivu.urls import canonical_url, parse_url

MELIA = "https://www.ivivu.com/khach-san-phu-quoc/khu-nghi-duong-melia-vinpearl-phu-quoc"


def test_hotel_page_is_recognised_and_canonicalised() -> None:
    u = parse_url(MELIA + "/?ci=2026-10-07&co=2026-10-08#rooms")
    assert u is not None
    assert u.channel == "ivivu"
    assert u.listing_key == "khach-san-phu-quoc/khu-nghi-duong-melia-vinpearl-phu-quoc"
    assert u.url == MELIA
    assert u.country_code == "vn"


def test_host_variants_and_case() -> None:
    u = parse_url("http://ivivu.com/Khach-San-Ho-Chi-Minh/Khach-San-Rex-Sai-Gon")
    assert u is not None and u.listing_key == "khach-san-ho-chi-minh/khach-san-rex-sai-gon"


def test_other_hosts_are_not_ivivu() -> None:
    assert parse_url("https://www.booking.com/hotel/vn/rex.html") is None
    assert parse_url("https://notivivu.com/khach-san-phu-quoc/x") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.ivivu.com/khach-san-phu-quoc",  # trang vùng
        "https://www.ivivu.com/",
        "https://www.ivivu.com/ve-may-bay/ha-noi-phu-quoc",
        "https://www.ivivu.com/khach-san-phu-quoc/a/b",
    ],
)
def test_ivivu_pages_that_are_not_a_hotel_raise(url: str) -> None:
    with pytest.raises(UnsupportedUrl, match="iVIVU"):
        parse_url(url)


def test_canonical_url() -> None:
    assert canonical_url("/khach-san-phu-quoc/x/") == "https://www.ivivu.com/khach-san-phu-quoc/x"
