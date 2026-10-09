"""Định danh khách sạn Booking (verify listing, D8) trên trang thật đã rút gọn."""

from decimal import Decimal
from pathlib import Path

from app.collector.booking.identity import parse_identity


def test_parse_identity_from_real_page(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "booking" / "meander_identity.html").read_text(encoding="utf-8")
    ident = parse_identity(html, "vn/meander-saigon")
    assert ident.external_id == "6309114"
    assert ident.name == "MEANDER Saigon"
    assert ident.url == "https://www.booking.com/hotel/vn/meander-saigon.html"
    assert ident.address == "3b Ly Tu Trong Street, District 1, Ho Chi Minh City, Vietnam"
    assert ident.city == "Ho Chi Minh Municipality"
    assert ident.country_code == "vn"
    assert (ident.lat, ident.lng) == (10.782456413688383, 106.70530772526168)
    assert ident.star_rating == Decimal("2")


def test_parse_identity_of_page_without_hotel() -> None:
    ident = parse_identity("<html><body>Page not found</body></html>", "vn/gone")
    assert ident.external_id is None and ident.name is None
    assert ident.lat is None and ident.star_rating is None


def test_name_falls_back_to_ld_json_and_unrated_hotel_has_no_stars() -> None:
    html = (
        '<script type="application/ld+json">{"@type": "Hotel", "name": "Rex Hotel"}</script>'
        "<script>hotel_class: 0,</script>"
    )
    ident = parse_identity(html, "vn/rex")
    assert ident.name == "Rex Hotel" and ident.star_rating is None and ident.address is None
