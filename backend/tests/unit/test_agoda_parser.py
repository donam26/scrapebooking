"""Parser trên JSON Agoda THẬT (bắt 2026-10-01 qua proxy VN, rút gọn theo whitelist trường, không
cookie/token). Số kỳ vọng đọc trực tiếp từ payload gốc trong lúc spike."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.collector.agoda.parser import (
    PayloadError,
    explicit_not_found,
    parse_identity,
    parse_property_data,
    parse_room_grid_sold_out,
    parse_suggest,
    property_id_from_html,
)
from app.domain.models import DemandKind, PageOutcome, StockScope


def _load(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / "agoda" / name).read_text(encoding="utf-8")


def test_melia_rooms_prices_and_stock(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "melia_2026-10-20.json"), adults=2)
    assert page.outcome == PageOutcome.ROOMS
    assert (page.external_id, page.currency) == ("1985199", "VND")
    assert page.hotel_name == "Melia Vinpearl Phú Quốc (Melia Vinpearl Phu Quoc)"
    assert (page.checkin, page.nights) == (date(2026, 10, 20), 1)
    # 6 loại phòng còn bán + 1 loại "Hết phòng"; badge = availability (số phòng Agoda còn bán).
    assert [(o.external_room_id, o.badge_count, o.dropdown_max) for o in page.offers] == [
        ("602208172", 10, None),
        ("602208202", 8, None),
        ("602208052", 20, None),
        ("602208197", 35, None),
        ("983925032", 2, None),  # "Chỉ còn lại 2 phòng!"
        ("983925033", 2, None),
        ("1013204462", 0, None),  # soldOutRooms
    ]
    assert all(o.stock_scope == StockScope.ROOM_TYPE for o in page.offers)
    villa = page.offers[0]
    assert villa.name.startswith("Biệt Thự 1 Phòng Ngủ Hướng Hồ")
    assert villa.max_occupancy == 2
    # 7 giá gốc, bỏ 3 giá cho 1 người lớn.
    assert len(villa.rates) == 4
    cheapest = villa.rates[0]
    assert cheapest.price == Decimal("4619882")  # gồm phí dịch vụ 5% + VAT 8% (4.073.970 chưa thuế)
    assert cheapest.taxes_included is True
    # Giá gạch 18.479.529 là COR "cao nhất ±30 ngày" (hiện -75%): không dùng làm giá gốc.
    assert cheapest.price_original is None
    assert cheapest.currency == "VND"
    assert (cheapest.refundable, cheapest.breakfast, cheapest.max_persons) == (False, True, 2)
    assert cheapest.name == "Non-refundable + breakfast"
    assert cheapest.promo_label == "Ưu đãi đặc biệt!"
    assert villa.min_price == Decimal("4619882")
    # Giá cho 4 người của villa 2 phòng ngủ vẫn là giá khách 2 người thấy được.
    assert page.offers[1].min_price == Decimal("6159881")
    assert page.offers[1].rates[0].max_persons == 4
    # Lần gọi này Agoda không trả visitorCount (24 giờ): chỉ có lượt đặt trong ngày.
    assert [(d.kind, d.value, d.window_hours) for d in page.demand_signals] == [
        (DemandKind.BOOKINGS_TODAY, Decimal(11), None)
    ]
    sold_out = page.offers[-1]
    assert sold_out.rates == () and sold_out.min_price is None


def test_multi_night_price_is_per_night_and_free_cancellation(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "caravelle_2026-10-24_2n.json"), adults=2)
    assert (page.hotel_name, page.nights) == ("Caravelle Saigon Hotel", 2)
    first = page.offers[0]
    rate = first.rates[0]
    # perBook gồm thuế 10.745.545 cho 2 đêm -> 5.372.773/đêm.
    assert rate.price == Decimal("5372773")
    assert (rate.refundable, rate.breakfast, rate.name) == (True, False, "Free cancellation")
    assert first.rates[1].name == "Free cancellation + breakfast"
    heritage = next(o for o in page.offers if o.external_room_id == "3370268")
    assert heritage.badge_count == 1  # "Phòng cuối cùng của chúng tôi!"
    exec_suite = next(o for o in page.offers if o.external_room_id == "3370250")
    assert exec_suite.rates[0].price_original is None
    assert first.rates[0].price_original is None  # giá gạch 10.000.000 cố định, không phải KM
    assert [(d.kind, d.value, d.window_hours, d.raw_text) for d in page.demand_signals] == [
        (DemandKind.BOOKINGS_24H, Decimal(8), 24, "8 du khách đã đặt hôm nay."),
        (DemandKind.BOOKINGS_TODAY, Decimal(8), None, "Đã được đặt 8 lần hôm nay"),
    ]


def test_campaign_label_and_rates_for_more_guests(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "campaign_2026-10-15.json"), adults=2)
    labels = {r.promo_label for o in page.offers for r in o.rates}
    assert labels == {"Mùa thu vàng"}
    studio = next(o for o in page.offers if o.external_room_id == "1390393979")
    rate = studio.rates[0]
    # Giá gốc 2.606.097 - "Mùa thu vàng" 694.959 (Agoda) - "Giảm giá phút chót" 799.203 (khách
    # sạn) = 1.111.935. Giá trước chiến dịch Agoda = 1.111.935 + 694.959.
    assert rate.price == Decimal("1111935")
    assert rate.price_original == Decimal("1806894")
    premier = next(o for o in page.offers if o.external_room_id == "1404668477")
    assert {r.max_persons for r in premier.rates} == {4}
    assert premier.badge_count == 5


def test_adults_none_keeps_every_rate(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "melia_2026-10-20.json"), adults=None)
    assert len(page.offers[0].rates) == 7
    assert min(r.max_persons or 0 for r in page.offers[0].rates) == 1


def test_currency_reported_when_agoda_ignores_request(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "melia_usd_2026-10-20.json"), adults=2)
    assert page.currency == "USD"
    assert page.offers[0].rates[0].currency == "USD"
    assert page.offers[0].rates[0].price == Decimal("177.91")


def test_property_sold_out_is_empty_grid_plus_room_grid_flag(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "camia_sold_out_2026-10-03.json"), adults=2)
    assert page.outcome == PageOutcome.EMPTY
    assert page.hotel_name == "Camia Resort & Spa"
    assert page.offers == ()
    assert parse_room_grid_sold_out(_load(fixtures_dir, "camia_room_grid_2026-10-03.json"))


def test_unknown_property_has_no_name(fixtures_dir: Path) -> None:
    page = parse_property_data(_load(fixtures_dir, "not_found.json"), adults=2)
    assert page.hotel_name is None
    assert page.outcome == PageOutcome.EMPTY
    assert page.complete  # isDataReady, không error: Agoda nói rõ id không tồn tại
    assert parse_identity(_load(fixtures_dir, "not_found.json")).name is None
    assert explicit_not_found(_load(fixtures_dir, "not_found.json"))


def test_incomplete_payload_without_name_is_not_explicit_not_found(fixtures_dir: Path) -> None:
    data = json.loads(_load(fixtures_dir, "not_found.json"))
    data["roomGridData"]["isDataReady"] = False
    assert not parse_property_data(json.dumps(data), adults=2).complete
    assert not explicit_not_found(json.dumps(data))
    data["roomGridData"]["isDataReady"] = True
    data["error"] = {"code": "RATE_LIMIT"}
    assert not explicit_not_found(json.dumps(data))
    # Payload bình thường (có tên): complete, không phải not_found.
    normal = _load(fixtures_dir, "melia_2026-10-20.json")
    assert parse_property_data(normal, adults=2).complete and not explicit_not_found(normal)


def test_payload_must_be_json_object() -> None:
    with pytest.raises(PayloadError):
        parse_property_data("<html>captcha</html>")
    with pytest.raises(PayloadError):
        parse_property_data("[]")


def test_identity_from_dateless_data(fixtures_dir: Path) -> None:
    identity = parse_identity(_load(fixtures_dir, "caravelle_dateless.json"))
    assert identity.external_id == "10971"
    assert identity.name == "Caravelle Saigon Hotel"
    assert identity.url == (
        "https://www.agoda.com/vi-vn/caravelle-saigon-hotel/hotel/ho-chi-minh-city-vn.html"
    )
    assert identity.address == "19-23 Công Trường Lam Sơn, Quận 1"
    assert (identity.city, identity.country_code) == ("Hồ Chí Minh", "vn")
    assert identity.lat == pytest.approx(10.7763, abs=1e-4)
    assert identity.lng == pytest.approx(106.7037, abs=1e-4)
    assert identity.star_rating == Decimal("5.0")


def test_identity_gives_canonical_slug_after_rename(fixtures_dir: Path) -> None:
    # URL "melia-vinpearl-phu-quoc" chuyển hướng về slug cũ của khách sạn.
    identity = parse_identity(_load(fixtures_dir, "melia_2026-10-20.json"))
    assert identity.url == (
        "https://www.agoda.com/vi-vn/vinpearl-discovery-2-phu-quoc_2/hotel/phu-quoc-island-vn.html"
    )


def test_suggest_keeps_only_hotels(fixtures_dir: Path) -> None:
    hits = parse_suggest(_load(fixtures_dir, "suggest_caravelle.json"))
    assert [(h.property_id, h.name, h.city, h.country_code) for h in hits] == [
        ("10971", "Caravelle Saigon Hotel", "Hồ Chí Minh", "vn")
    ]


def test_property_id_from_page_html(fixtures_dir: Path) -> None:
    assert property_id_from_html(_load(fixtures_dir, "property_page_snippet.html")) == "1985199"
    assert property_id_from_html("<html></html>") is None
