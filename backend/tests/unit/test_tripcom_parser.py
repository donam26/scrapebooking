import copy
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.collector.tripcom.parser import (
    HotelPage,
    RoomListResult,
    build_payload,
    demand_signals,
    last_booked_minutes,
    parse_hotel_page,
    parse_probe_payload,
    parse_room_list,
    parse_suggest,
)
from app.domain.models import DemandKind, DemandSignal, ProbeStatus
from tests.conftest import FIXTURES_DIR

FIX = FIXTURES_DIR / "tripcom"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIX / name).read_text())
    return data


def parse(
    name: str, adults: int = 2, nights: int = 1, checkin: date | None = None
) -> RoomListResult:
    return parse_room_list(
        load(name), currency="VND", adults=adults, nights=nights, checkin=checkin
    )


def test_hotel_page_from_ssr_flight_data() -> None:
    page = parse_hotel_page((FIX / "detail_melia.html").read_text())
    assert page == HotelPage(
        hotel_id="7047736",
        name="Meliá Vinpearl Phu Quoc",
        name_en="Melia Vinpearl Phu Quoc",
        address="Bãi Dài, Đảo Phú Quốc, An Giang",
        city="Đảo Phú Quốc",
        country_code="vn",
        lat=10.357969,
        lng=103.849616,
        star_rating=Decimal("5"),
        last_booking="Lần đặt gần nhất cách đây 18 phút",
    )


def test_hotel_page_without_data() -> None:
    page = parse_hotel_page("<html><body>Trip.com</body></html>")
    assert page.hotel_id is None and page.name is None


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("Lần đặt gần nhất cách đây 18 phút", 18),
        ("Được đặt lần gần nhất 15 giờ trước", 900),
        ("Lần đặt gần nhất cách đây 2 ngày", 2880),
        ("Last booked 3 hours ago", 180),
        ("Đặt ngay hôm nay", None),
    ],
)
def test_last_booked_minutes(text: str, minutes: int | None) -> None:
    assert last_booked_minutes(text) == minutes


def test_last_booked_demand_signal() -> None:
    page = parse_hotel_page((FIX / "detail_melia.html").read_text())
    assert demand_signals(page) == (
        DemandSignal(
            kind=DemandKind.LAST_BOOKED_MINUTES,
            value=Decimal(18),
            window_hours=None,
            stay_date=None,
            raw_text="Lần đặt gần nhất cách đây 18 phút",
        ),
    )
    hours = HotelPage(hotel_id="1", name="x", last_booking="Được đặt lần gần nhất 15 giờ trước")
    assert demand_signals(hours)[0].value == Decimal(900)


@pytest.mark.parametrize("label", [None, "Đặt ngay hôm nay"])
def test_no_demand_signal_without_last_booking(label: str | None) -> None:
    assert demand_signals(HotelPage(hotel_id="1", name="x", last_booking=label)) == ()


def test_melia_one_night_prices_include_taxes_per_room_type() -> None:
    result = parse("roomlist_melia_1n.json", checkin=date(2026, 10, 15))
    assert result.status == ProbeStatus.OK
    assert [o.external_room_id for o in result.offers] == ["528714841", "517430368"]
    villa1, villa3 = result.offers
    assert villa1.name.startswith("Biệt Thự 1 Phòng Ngủ")
    assert villa1.stock_scope == "rate"
    assert (villa1.badge_count, villa1.dropdown_max, villa1.max_occupancy) == (9, 9, 6)
    assert (villa3.badge_count, villa3.dropdown_max) == (2, 2)
    cheapest = villa1.rates[0]
    # priceInfo.price 4.074.074 chưa thuế; comparingAmount 4.620.000 gồm VAT + phí dịch vụ.
    assert cheapest.price == Decimal(4620000)
    assert cheapest.currency == "VND"
    assert cheapest.taxes_included is True
    assert cheapest.refundable is False
    assert cheapest.breakfast is True
    assert cheapest.max_persons == 2
    assert cheapest.price_original is None and cheapest.promo_label is None
    assert cheapest.name == "Không hoàn tiền + bữa sáng"
    assert villa1.min_price == Decimal(4620000)
    # Mức 1 khách chỉ nằm trong compensatedRooms, không ở roomList → không có trong offers.
    assert all(r.max_persons is not None and r.max_persons >= 2 for r in villa1.rates)
    assert len(villa1.rates) == 6


def test_rates_for_fewer_guests_than_adults_are_dropped() -> None:
    result = parse("roomlist_melia_1n.json", adults=3)
    villa1 = result.offers[0]
    assert [r.max_persons for r in villa1.rates] == [6, 3, 4]
    assert villa1.badge_count == 9  # tồn phòng vẫn tính từ mọi mức đặt được


def test_multi_night_price_is_per_night() -> None:
    result = parse("roomlist_melia_2n.json", nights=2, checkin=date(2026, 10, 22))
    (offer,) = result.offers
    assert offer.rates[0].price == Decimal(4620000)  # comparingAmount 9.240.000 / 2 đêm
    assert offer.badge_count == 8


def test_hotel_packages_priced_with_package_label() -> None:
    result = parse("roomlist_caravelle.json")
    assert result.status == ProbeStatus.OK
    by_id = {o.external_room_id: o for o in result.offers}
    # Mức hết phòng (isFullRoom, 9999) không nằm trong roomList → không có loại phòng 27996424.
    assert set(by_id) == {"246503329", "23072017", "27997118"}
    opera = by_id["246503329"]
    assert (opera.badge_count, opera.dropdown_max) == (17, 10)  # số còn vượt trần ô chọn
    assert [r.price for r in opera.rates] == [Decimal(7065564), Decimal(7948759)]
    assert [r.breakfast for r in opera.rates] == [False, True]
    assert all(r.refundable for r in opera.rates)
    assert all(r.promo_label is None for r in opera.rates)
    # Loại phòng chỉ bán "Gói Khách Sạn" (lounge) vẫn có giá, nhãn là tên gói.
    signature = by_id["23072017"]
    (package,) = signature.rates
    assert package.price == Decimal(10460291)
    assert package.taxes_included is True and package.breakfast is True
    assert package.promo_label == "Gói khách sạn: Đặc quyền Signature Lounge (Mỗi ngày 2)"
    assert signature.badge_count == 29
    suite = by_id["27997118"]
    assert (suite.badge_count, suite.dropdown_max, suite.max_occupancy) == (1, 1, 4)


@pytest.mark.parametrize(
    ("pk_type", "item"),
    [
        (1, "Đặc quyền Signature Lounge"),  # loại gói khác "Gói Khách Sạn"
        (2, "Đưa đón sân bay khứ hồi"),
        (2, "Vé máy bay khứ hồi SGN-PQC"),
        (2, "City tour nửa ngày"),
    ],
)
def test_flight_transfer_tour_combos_are_excluded(pk_type: int, item: str) -> None:
    doc = load("roomlist_caravelle.json")
    sale = doc["data"]["saleRoomMap"]["1513186827_O3VT66-Z-1-BEE4AZ"]
    sale["xProOption"]["pkType"] = pk_type
    sale["xProOption"]["xProducts"][1]["name"] = item
    result = parse_room_list(doc, currency="VND", adults=2, nights=1)
    signature = next(o for o in result.offers if o.external_room_id == "23072017")
    assert signature.rates == ()
    assert signature.badge_count == 29  # vẫn giữ tồn phòng


def test_promotion_original_price_and_label() -> None:
    result = parse("roomlist_muongthanh.json")
    deluxe = result.offers[0]
    assert deluxe.external_room_id == "95378465"
    assert deluxe.badge_count == 3  # = "Chỉ còn 3 phòng có giá này" ở trang danh sách
    promo, plain, flash = deluxe.rates
    assert promo.price == Decimal(1260000)
    # deletePrice 3.906.667 (chưa thuế) quy về gồm thuế theo tỉ lệ 1.260.000 / 1.166.667.
    assert promo.price_original == Decimal(4219199)
    assert promo.promo_label == "Ưu đãi đặt phòng sớm"
    assert plain.price == Decimal(1276001)
    assert plain.price_original is None and plain.promo_label is None
    assert flash.price_original == Decimal(4192001)
    assert flash.promo_label == "Ưu Đãi Giới Hạn Thời Gian"
    triple = result.offers[1]
    assert triple.rates[0].price_original == Decimal(6032944)
    assert triple.rates[0].promo_label == "Ưu đãi đặt phòng sớm"  # mức có 2 KM: lấy cái đầu
    pay_at_hotel = triple.rates[1]
    assert pay_at_hotel.price == Decimal(1818300) and pay_at_hotel.taxes_included is True


def test_spider_block_is_blocked() -> None:
    result = parse("roomlist_spider_blocked.json")
    assert result.status == ProbeStatus.BLOCKED
    assert result.offers == ()


def test_currency_mismatch_is_error() -> None:
    doc = load("roomlist_muongthanh.json")
    for sale in doc["data"]["saleRoomMap"].values():
        sale["priceInfo"]["currency"] = "USD"
    result = parse_room_list(doc, currency="VND", adults=2, nights=1)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "currency_mismatch:USD"


def test_other_search_dates_are_error() -> None:
    result = parse("roomlist_melia_1n.json", checkin=date(2026, 10, 16))
    assert result.status == ProbeStatus.ERROR
    assert result.error is not None and "20261015" in result.error


@pytest.mark.parametrize(
    ("sold_out", "status"), [(True, ProbeStatus.SOLD_OUT), (False, ProbeStatus.NO_ROOMS_1N)]
)
def test_empty_room_list(sold_out: bool, status: ProbeStatus) -> None:
    doc = load("roomlist_melia_1n.json")
    doc["data"]["roomList"] = []
    doc["data"]["isRoomListSoldOut"] = sold_out
    assert parse_room_list(doc, currency="VND", adults=2, nights=1).status == status


def test_all_rates_full_is_sold_out() -> None:
    doc = load("roomlist_melia_2n.json")
    for sale in doc["data"]["saleRoomMap"].values():
        sale["bookingStatusInfo"]["isFullRoom"] = True
    assert parse_room_list(doc, currency="VND", adults=2, nights=2).status == ProbeStatus.SOLD_OUT


def test_payload_roundtrip() -> None:
    raw = (FIX / "roomlist_muongthanh.json").read_text()
    page = HotelPage(hotel_id="6648653", name="Mường Thanh Luxury Phú Quốc", last_booking=None)
    parsed = parse_probe_payload(
        build_payload(page, raw), currency="VND", adults=2, nights=1, checkin=date(2026, 10, 15)
    )
    assert parsed.page.hotel_id == "6648653"
    assert parsed.page.name == "Mường Thanh Luxury Phú Quốc"
    assert parsed.result == parse("roomlist_muongthanh.json")
    bare = parse_probe_payload(raw, currency="VND", adults=2, nights=1)
    assert bare.result.offers == parsed.result.offers


def test_suggest_hits() -> None:
    (melia,) = parse_suggest(load("suggest_melia.json"))
    assert melia.hotel_id == "7047736"
    assert melia.name == "Meliá Vinpearl Phu Quoc"
    assert melia.subtitle == "Đảo Phú Quốc, An Giang, Việt Nam"
    assert (melia.lat, melia.lng, melia.country_code) == (10.357969, 103.849616, "vn")
    (caravelle,) = parse_suggest(load("suggest_caravelle.json"))
    assert (caravelle.hotel_id, caravelle.name) == ("839839", "Caravelle Saigon")


def test_suggest_skips_non_hotel_keywords() -> None:
    doc = load("suggest_melia.json")
    city = copy.deepcopy(doc["data"]["mainKeywordList"]["keywords"][0])
    city["keyword"]["hotelInfo"] = {}
    city["keyword"]["keywordContentInfo"]["tripType"] = "D"
    doc["data"]["mainKeywordList"]["keywords"].insert(0, city)
    assert [h.hotel_id for h in parse_suggest(doc)] == ["7047736"]
