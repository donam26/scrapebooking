import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.collector.mytour.api import app_hash, availability_body
from app.collector.mytour.parser import parse_availability, parse_identity, parse_suggestions
from app.domain.models import DemandKind, StockScope

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mytour"
# Lúc chụp payload Sol by Melia; trang khi đó hiện "Vừa được đặt 13 giờ trước".
CAPTURED_AT = datetime.fromtimestamp(1790841306, UTC)


def _data(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return payload["data"]  # type: ignore[no-any-return]


def test_app_hash_matches_browser_header() -> None:
    # Header appHash trình duyệt gửi lúc 1790841233 (01/10/2026), khoá làm tròn 5 phút.
    assert app_hash(1790841233.3) == "C/FL1WG1kR27OGbU7Wxp09GpXz7Wn80ttzlQKPbShio="
    assert app_hash(1790841000) == app_hash(1790841299)


def test_availability_body_uses_mytour_date_format() -> None:
    body = availability_body(239, date(2026, 10, 13), 2, 2)
    assert body["checkIn"] == "13-10-2026"
    assert body["checkOut"] == "15-10-2026"
    assert (body["hotelId"], body["adults"], body["rooms"], body["children"]) == (239, 2, 1, 0)


def test_parse_sol_by_melia_rooms_and_rates() -> None:
    result = parse_availability(_data("availability_sol_by_melia_1n.json"), 2, "VND", CAPTURED_AT)
    assert result.completed
    assert len(result.offers) == 13
    standard = next(o for o in result.offers if o.external_room_id == "41039")
    assert standard.name == "Standard Room"
    assert standard.max_occupancy == 2
    assert standard.stock_scope == StockScope.RATE
    assert standard.dropdown_max is None
    # 8 giá, bỏ 1 giá phải đăng nhập (hiddenPrice)
    assert len(standard.rates) == 7
    cheapest = standard.rates[0]
    assert cheapest.price == Decimal("1808000")
    assert cheapest.currency == "VND"
    assert cheapest.price_original == Decimal("1967000")
    assert cheapest.taxes_included is True
    assert cheapest.breakfast is True
    assert cheapest.refundable is False  # "Hoàn huỷ một phần": không miễn phí huỷ
    assert cheapest.promo_label == "CHAMTHU26"
    assert cheapest.source_supplier == "ta:27"
    assert cheapest.name == "Hoàn huỷ một phần · Bữa sáng"
    # Số phòng còn: lớn nhất trong các nguồn ("Chỉ còn N phòng trống")
    assert standard.badge_count == 7


def test_hidden_member_prices_are_excluded() -> None:
    data = _data("availability_sol_by_melia_1n.json")
    rates = [r for room in data["items"] for r in room["rates"]]
    hidden = [r for r in rates if r["hiddenPrice"]]
    result = parse_availability(data, 2, "VND", CAPTURED_AT)
    assert len(hidden) == 6  # "Đăng nhập để giảm…"
    assert sum(len(o.rates) for o in result.offers) == len(rates) - len(hidden)


def test_rates_for_fewer_adults_are_excluded() -> None:
    result = parse_availability(_data("availability_sol_by_melia_1n.json"), 3, "VND", CAPTURED_AT)
    assert result.offers == ()  # mọi phòng tối đa 2 khách


def test_price_is_per_night_for_multi_night_stay() -> None:
    result = parse_availability(_data("availability_rex_2n.json"), 2, "VND", CAPTURED_AT)
    deluxe = next(o for o in result.offers if o.external_room_id == "180441035")
    assert deluxe.min_price == Decimal("3781000")  # tổng 2 đêm sau KM = 7.562.000


def test_pending_and_empty_payloads() -> None:
    pending = parse_availability(_data("availability_pending.json"), 2, "VND", CAPTURED_AT)
    assert not pending.completed and pending.offers == ()
    empty = parse_availability(_data("availability_empty.json"), 2, "VND", CAPTURED_AT)
    assert empty.completed and empty.offers == ()


def test_currency_comes_from_formatted_price() -> None:
    data = _data("availability_rex_2n.json")
    for room in data["items"]:
        for rate in room["rates"]:
            rate["formattedPrice"] = "155 USD"
    result = parse_availability(data, 2, "VND", CAPTURED_AT)
    assert {r.currency for o in result.offers for r in o.rates} == {"USD"}


def test_parse_identity_from_detail() -> None:
    identity = parse_identity(_data("detail_sol_by_melia.json"))
    assert identity.external_id == "23812"
    assert identity.name == "SOL By Melia Phu Quoc"
    assert identity.url == "https://mytour.vn/khach-san/23812-sol-by-melia-phu-quoc.html"
    assert identity.city == "Kiên Giang"
    assert identity.country_code == "vn"
    assert identity.star_rating == Decimal("5")
    assert identity.lat is not None and abs(identity.lat - 10.146) < 0.001


def test_parse_suggestions_keeps_hotels() -> None:
    [s] = parse_suggestions(_data("suggest_melia_vinpearl.json"))
    assert s.hotel_id == 40668
    assert s.name == "Melia Vinpearl Phú Quốc"
    assert s.url == "https://mytour.vn/khach-san/40668-melia-vinpearl-phu-quoc.html"
    assert s.country_code == "vn"
    assert s.lat == 10.355272


def test_last_booked_signal_uses_real_age_and_page_label() -> None:
    result = parse_availability(_data("availability_sol_by_melia_1n.json"), 2, "VND", CAPTURED_AT)
    [signal] = result.demand_signals
    assert signal.kind == DemandKind.LAST_BOOKED_MINUTES
    assert signal.value == Decimal(3790)  # 63 giờ 10 phút thật
    assert signal.raw_text == "Vừa được đặt 13 giờ trước"  # web chia 5 khoảng thời gian
    assert signal.window_hours is None and signal.stay_date is None


def test_last_booked_older_than_five_days_is_not_shown() -> None:
    # Rex: lần đặt cuối ~13 ngày trước lúc chụp → web không hiện dòng "Vừa được đặt"
    result = parse_availability(_data("availability_rex_2n.json"), 2, "VND", CAPTURED_AT)
    assert result.demand_signals == ()
    empty = parse_availability(_data("availability_empty.json"), 2, "VND", CAPTURED_AT)
    assert empty.demand_signals == ()
