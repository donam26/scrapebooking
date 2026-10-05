"""Parser ivivu trên payload thật đã cắt gọn (tests/fixtures/ivivu, lấy 01/10/2026 qua proxy VN).

Số kỳ vọng đọc thẳng từ JSON gốc: giá web hiện "Giá 1 đêm / 1 villa 3.120.500" = PriceAvgPlusTA
của dòng đầu hạng phòng 13361."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.collector.ivivu.api import price_headers, price_request
from app.collector.ivivu.parser import (
    bookings_month_signal,
    is_invalid_token,
    parse_hotel_page,
    parse_price_response,
    parse_search,
    room_class_id,
    top_sale_signal,
    trim_price_payload,
)
from app.domain.models import DemandKind, ProbeStatus


def _read(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / "ivivu" / name).read_text()


def _price(fixtures_dir: Path) -> str:
    return _read(fixtures_dir, "price_melia_2026-10-12.json")


def test_melia_offers_rates_and_suppliers(fixtures_dir: Path) -> None:
    parsed = parse_price_response(_price(fixtures_dir), adults=2, currency="VND")
    assert parsed.status == ProbeStatus.OK
    assert parsed.hotel_name == "Khu nghỉ dưỡng Melia Vinpearl Phú Quốc"
    by_id = {o.external_room_id: o for o in parsed.offers}
    villa = by_id["13361"]
    assert villa.name == "One Bedroom Villa with Private Pool"
    assert villa.max_occupancy == 2
    assert len(villa.rates) == 59
    assert villa.min_price == Decimal("3120500")
    assert villa.min_refundable_price == Decimal("4537500")
    assert villa.badge_count is None and villa.dropdown_max is None
    cheapest = villa.rates[0]  # rates sắp theo giá
    assert cheapest.price == Decimal("3120500") and cheapest.currency == "VND"
    assert cheapest.source_supplier == "B2B"
    assert cheapest.refundable is False and cheapest.breakfast is True
    assert cheapest.taxes_included is True and cheapest.max_persons == 2
    assert cheapest.promo_label == "Ưu Đãi Mùa Hè (Dành cho khách Việt Nam)"
    suppliers = {r.source_supplier for r in villa.rates}
    assert suppliers == {"B2B", "AGODA", "IVIVU", "MGB", "HBED"}  # AGD → AGODA, Internal → IVIVU
    agoda = [r for r in villa.rates if r.source_supplier == "AGODA"]
    assert all(r.max_persons is None for r in agoda)  # Agoda không ghi số người (Adults=0)
    assert [o.min_price for o in parsed.offers] == sorted(o.min_price for o in parsed.offers)


def test_room_only_and_discounted_rates(fixtures_dir: Path) -> None:
    villa = next(
        o
        for o in parse_price_response(_price(fixtures_dir), 2, "VND").offers
        if o.external_room_id == "13361"
    )
    room_only = [r for r in villa.rates if r.name == "Không bao gồm ăn sáng"]
    assert len(room_only) == 5 and all(r.breakfast is False for r in room_only)
    discounted = next(r for r in villa.rates if r.price == Decimal("3344000"))
    assert discounted.price_original == Decimal("4104000")  # + PriceDiscount 760.000
    assert discounted.source_supplier == "IVIVU"


def test_unmatched_supplier_room_gets_name_key(fixtures_dir: Path) -> None:
    # ClassID âm (-105) được ivivu đánh số lại mỗi lần gọi: khoá theo tên.
    parsed = parse_price_response(_price(fixtures_dir), 2, "VND")
    keys = [o.external_room_id for o in parsed.offers]
    assert "-105" not in keys
    assert (
        "name:1-bedroom-villa-with-lake-view-full-double-bed-king-size-bed-private-pool-welcome-drink"
        in keys
    )
    assert room_class_id({"ClassID": "-7", "ClassName": "Phòng Đôi Hướng Biển"}) == (
        "name:phong-doi-huong-bien"
    )


def test_rates_for_fewer_persons_than_adults_are_dropped(fixtures_dir: Path) -> None:
    parsed = parse_price_response(_price(fixtures_dir), adults=3, currency="VND")
    by_id = {o.external_room_id: o for o in parsed.offers}
    assert len(by_id["13361"].rates) == 6  # chỉ còn Agoda (không ghi số người)
    assert len(by_id["1074"].rates) == 26  # giá villa cho 4 người lớn + Agoda
    assert len(by_id) == 2  # phòng MGB 2 người bị bỏ hẳn


def test_package_rates_are_excluded(fixtures_dir: Path) -> None:
    data = json.loads(_price(fixtures_dir))
    for rc in data["Hotels"][0]["RoomClasses"]:
        for r in rc["MealTypeRates"]:
            r["IsComboFlight"] = True
    parsed = parse_price_response(json.dumps(data), 2, "VND")
    assert parsed.status == ProbeStatus.SOLD_OUT and parsed.offers == ()


def test_currency_mismatch_is_an_error(fixtures_dir: Path) -> None:
    data = json.loads(_price(fixtures_dir))
    data["Hotels"][0]["RoomClasses"][0]["CurrencyCode"] = "USD"
    parsed = parse_price_response(json.dumps(data), 2, "VND")
    assert parsed.status == ProbeStatus.ERROR and parsed.error == "currency_mismatch:USD"


def test_taxes_flag_follows_exclude_vat(fixtures_dir: Path) -> None:
    data = json.loads(_price(fixtures_dir))
    data["Hotels"][0]["ExcludeVAT"] = 1
    parsed = parse_price_response(json.dumps(data), 2, "VND")
    assert {r.taxes_included for o in parsed.offers for r in o.rates} == {False}


def test_empty_hotels_is_sold_out_and_garbage_is_error() -> None:
    assert parse_price_response('{"Hotels":[],"MSG":""}', 2, "VND").status == ProbeStatus.SOLD_OUT
    assert parse_price_response("<html>", 2, "VND").error == "invalid_json"
    err = parse_price_response('{"status":"error","error_code":"X"}', 2, "VND")
    assert err.status == ProbeStatus.ERROR and err.error == "api: X"


def test_trimmed_payload_reparses_identically(fixtures_dir: Path) -> None:
    raw = _price(fixtures_dir)
    trimmed = trim_price_payload(raw)
    assert len(trimmed) < len(raw)
    assert parse_price_response(trimmed, 2, "VND") == parse_price_response(raw, 2, "VND")
    assert trim_price_payload("not json") == "not json"


def test_invalid_token_response(fixtures_dir: Path) -> None:
    body = _read(fixtures_dir, "invalid_token_403.json")
    assert is_invalid_token(403, body)
    assert not is_invalid_token(200, body)
    assert not is_invalid_token(403, "<html>cloudflare</html>")


def test_hotel_page_identity(fixtures_dir: Path) -> None:
    identity = parse_hotel_page(_read(fixtures_dir, "hotel_page_melia.html"))
    assert identity is not None
    assert identity.external_id == "377594"
    assert identity.name == "Khu nghỉ dưỡng Melia Vinpearl Phú Quốc"
    assert identity.url == (
        "https://www.ivivu.com/khach-san-phu-quoc/khu-nghi-duong-melia-vinpearl-phu-quoc"
    )
    assert identity.address == "Khu Bãi Dài, xã Gành Dầu, huyện Phú Quốc, Kiên Giang"
    assert identity.city == "Phú Quốc"
    assert identity.country_code == "vn"
    assert identity.lat == 10.3579746 and identity.lng == 103.84963725
    assert identity.star_rating == Decimal("5")
    assert parse_hotel_page("<html><body>no state</body></html>") is None


def test_search_and_demand_signals(fixtures_dir: Path) -> None:
    items = parse_search(_read(fixtures_dir, "searchhotel_melia.json"))
    assert [i["hotelId"] for i in items][:2] == [377594, 577334]
    month = bookings_month_signal(items[0])
    assert month is not None
    assert month.kind == DemandKind.BOOKINGS_MONTH and month.value == Decimal(17)
    sold = top_sale_signal(_read(fixtures_dir, "topsale24h_melia.json"))
    assert sold is not None
    assert sold.kind == DemandKind.ROOMS_SOLD_24H
    assert sold.value == Decimal(2) and sold.window_hours == 24 and sold.stay_date is None
    assert sold.raw_text is not None and "Đã bán 2 phòng" in sold.raw_text
    assert parse_search('[{"type":2,"regionName":"Phú Quốc"}]') == []
    assert top_sale_signal("oops") is None


def test_price_request_matches_web_payload() -> None:
    body = price_request(377594, date(2026, 10, 7), nights=2, adults=2)
    assert body["hotelID"] == 377594
    assert (body["checkInDate"], body["checkOutDate"]) == ("2026-10-07", "2026-10-09")
    assert body["roomsRequest"][0]["adults"]["value"] == 2
    assert body["roomsRequest"][0]["child"]["value"] == 0
    assert body["isPackageRate"] is False and body["roomNumber"] == 1
    assert price_headers("tok")["X-ivv-key"] == "tok"
    assert "X-ivv-key" not in price_headers("")


def test_isshowprices_zero_rates_are_kept_regression_park_hyatt() -> None:
    """01/10/2026: mọi giá của Park Hyatt có Isshowprices=0 nhưng đặt được (AGD 10.206.000 = giá
    trên Agoda/Trip.com). Lọc theo cờ này làm khách sạn bị coi là hết phòng."""
    from pathlib import Path

    from app.collector.ivivu.parser import parse_price_response
    from app.domain.models import ProbeStatus

    text = (
        Path(__file__).parent.parent / "fixtures" / "ivivu" / "price_parkhyatt_2026-10-01.json"
    ).read_text()
    parsed = parse_price_response(text, 2, "VND")
    assert parsed.status == ProbeStatus.OK
    cheapest = min(r.price for o in parsed.offers for r in o.rates)
    assert str(cheapest) == "10206000"
