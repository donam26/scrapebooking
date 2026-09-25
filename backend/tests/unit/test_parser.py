"""Parser trên HTML Booking.com THẬT (bắt 2026-09-25 qua proxy dân dụng VN, rút gọn bằng
scripts/capture_fixture.py). Số kỳ vọng được trích độc lập từ HTML (không qua parser)."""

import gzip
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.collector.booking.parser import page_to_dict, parse_hotel_page
from app.collector.booking.selectors import page_checkin
from app.domain.models import PageOutcome

FIXTURES = [
    "reverie_2026-10-10",
    "park-hyatt_2026-11-05",
    "jovia_sold_out_2026-10-03",
    "reverie_2026-09-25_last_minute",
    "rex_2026-09-25_partner_offers",
    "caravelle_2026-10-10",
]


def _load(fixtures_dir: Path, name: str) -> str:
    return gzip.decompress((fixtures_dir / "html" / f"{name}.html.gz").read_bytes()).decode("utf-8")


def test_reverie_room_types_badges_and_dropdowns(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "reverie_2026-10-10"), "VND", adults=2)
    assert page.outcome == PageOutcome.ROOMS
    assert page.booking_hotel_id == "1191026"
    assert page.hotel_name == "The Reverie Saigon - The Leading Hotels of the World"
    assert page.csrf_token
    # Mỗi loại phòng một offer (ô loại phòng thật là <th rowspan=…>, không phải <td>).
    assert [(o.booking_room_id, o.badge_count, o.dropdown_max) for o in page.offers] == [
        ("119102603", 2, 2),  # "We have 2 left"
        ("119102607", None, 10),  # không có nhãn, dropdown chạm trần
        ("119102604", 5, 5),
        ("119102605", 3, 3),
        ("119102606", 1, 1),
        ("119102609", 3, 3),
        ("119102639", 4, 4),
        ("119102610", 3, 3),
        ("119102641", 4, 4),
        ("119102611", 1, 1),
    ]
    assert page.offers[0].name == "Deluxe Twin Room High Floor"
    assert page.offers[0].max_occupancy == 2


def test_reverie_rates_only_for_searched_party(fixtures_dir: Path) -> None:
    # Bảng có cả dòng "Only for 1 guest" (rẻ hơn ở hạng suite); tìm cho 2 người lớn thì bỏ.
    page = parse_hotel_page(_load(fixtures_dir, "reverie_2026-10-10"), "VND", adults=2)
    twin = page.offers[0]
    assert [(r.name, r.price, r.refundable, r.breakfast, r.max_persons) for r in twin.rates] == [
        ("Non-refundable", Decimal("8879220"), False, None, 2),
        ("Free cancellation", Decimal("9865800"), True, None, 2),
        ("Non-refundable + breakfast", Decimal("10807020"), False, True, 2),
        ("Free cancellation + breakfast", Decimal("11793600"), True, True, 2),
    ]
    assert twin.min_price == Decimal("8879220")
    assert twin.min_refundable_price == Decimal("9865800")
    junior = page.offers[5]
    assert junior.min_price == Decimal("15583428")  # không phải 14619528 (giá 1 khách)
    assert junior.min_refundable_price == Decimal("17100720")
    assert all(r.currency == "VND" for o in page.offers for r in o.rates)


def test_without_party_size_all_rates_kept(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "reverie_2026-10-10"), "VND")
    assert len(page.offers[0].rates) == 6
    assert page.offers[5].min_price == Decimal("14619528")


def test_park_hyatt_nine_room_types(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "park-hyatt_2026-11-05"), "VND", adults=2)
    assert page.outcome == PageOutcome.ROOMS and page.booking_hotel_id == "345986"
    assert page.hotel_name == "Park Hyatt Saigon"
    assert [(o.name, o.badge_count, o.dropdown_max, o.min_price) for o in page.offers] == [
        ("Twin Room", 5, 5, Decimal("10650000")),
        ("King Room with City View", None, 9, Decimal("12300000")),
        ("Twin Room with City View", None, 9, Decimal("12300000")),
        ("King Room with Garden View", None, 9, Decimal("12600000")),
        ("Twin Room with Garden View", 4, 4, Decimal("12600000")),
        ("Deluxe King Room", None, 8, Decimal("17950000")),
        ("Suite", 2, 2, Decimal("21100000")),
        ("Suite", 2, 2, Decimal("23100000")),
        ("Executive Suite", 5, 5, Decimal("31400000")),
    ]
    assert all(len(o.rates) == 2 for o in page.offers)


def test_last_minute_layout(fixtures_dir: Path) -> None:
    # Nhận phòng trong ngày: không có cột "Max persons" (sức chứa ở "Sleeps: 2 adults" trong ô loại
    # phòng), giá có giá gạch (bui-price-display__original) và "Total cost to cancel".
    page = parse_hotel_page(_load(fixtures_dir, "reverie_2026-09-25_last_minute"), "VND", adults=2)
    assert page.outcome == PageOutcome.ROOMS and len(page.offers) == 6
    assert all(o.max_occupancy == 2 for o in page.offers)
    twin = page.offers[0]
    assert (twin.badge_count, twin.dropdown_max) == (4, 4)
    assert [(r.price, r.refundable, r.breakfast, r.max_persons) for r in twin.rates] == [
        (Decimal("8699198"), False, None, 2),  # giá hiện tại, không phải giá gạch 9157050
        (Decimal("10439037"), False, True, 2),
    ]
    romance = page.offers[2]
    assert (romance.badge_count, romance.dropdown_max) == (3, 3)  # nhãn nằm ở ô điều kiện


def test_partner_offers_are_not_the_hotels_own_rooms(fixtures_dir: Path) -> None:
    # "Booking Basic" (data-block-id chứa "bbasic", "Partner offer", không có dropdown): giá đối tác
    # bán lại, không phải giá/tồn kho của khách sạn. Nhóm chỉ có giá đối tác thì bỏ; ID loại phòng
    # lấy từ dòng giá của chính khách sạn (trước đây cả nhóm bị gán ID "bbasic").
    page = parse_hotel_page(_load(fixtures_dir, "rex_2026-09-25_partner_offers"), "VND", adults=2)
    assert [
        (o.booking_room_id, o.badge_count, o.dropdown_max, o.min_price) for o in page.offers
    ] == [
        ("7100514", None, 10, Decimal("4000577")),  # không phải giá đối tác 3588262
        ("7100411", 2, 2, Decimal("4516781")),
        ("7100515", 2, 2, Decimal("4516781")),
        ("7100412", None, 10, Decimal("4774883")),
        ("7100413", None, 10, Decimal("5032984")),
        ("7100516", None, 10, Decimal("5032984")),
        ("7100414", 3, 3, Decimal("6388074")),
    ]
    assert all(len(o.rates) == 1 for o in page.offers)


def test_caravelle_skips_partner_only_group(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "caravelle_2026-10-10"), "VND", adults=2)
    assert [
        (o.booking_room_id, o.badge_count, o.dropdown_max, o.min_price) for o in page.offers
    ] == [
        ("7433301", None, 10, Decimal("4681831")),
        ("7433317", None, 10, Decimal("4681831")),
        ("7433308", None, 10, Decimal("4942261")),
        ("7433318", None, 10, Decimal("4941933")),
        ("7433303", None, 10, Decimal("6632594")),
        ("7433319", 5, 5, Decimal("6632594")),
        ("7433320", None, 10, Decimal("7933103")),
        ("7433310", None, 9, Decimal("10013916")),
        ("7433304", None, 8, Decimal("11054323")),
        ("7433309", None, 10, Decimal("8713408")),
        ("7433311", 1, 1, Decimal("12094730")),
    ]


def test_real_sold_out_page(fixtures_dir: Path) -> None:
    # "We have no availability here between Sat 3 Oct 2026 and Sun 4 Oct 2026" (#no_availability_msg)
    page = parse_hotel_page(_load(fixtures_dir, "jovia_sold_out_2026-10-03"), "VND", adults=2)
    assert page.outcome == PageOutcome.SOLD_OUT
    assert page.offers == ()
    assert page.hotel_name == "Jovia Hotel" and page.booking_hotel_id == "9467659"


def test_page_whose_dates_were_dropped_is_not_sold_out(fixtures_dir: Path) -> None:
    # Booking nghi bot 301 về URL trần: không có bảng giá, checkin rỗng. Không được hiểu là hết phòng.
    html = _load(fixtures_dir, "reverie_dates_dropped")
    assert page_checkin(html) == ""
    assert parse_hotel_page(html, "VND", adults=2).outcome == PageOutcome.EMPTY


def test_free_cancellation_wins_over_cancel_cost_text() -> None:
    # Ô điều kiện chứa cả popup chính sách: "Free cancellation" phải thắng "Total cost to cancel".
    html = (
        '<table id="hprt-table"><tbody><tr data-block-id="111_1_2_0">'
        '<th class="hprt-table-cell-roomtype"><a class="hprt-roomtype-link" data-room-id="111">'
        '<span class="hprt-roomtype-icon-link">Deluxe</span></a></th>'
        '<td class="hprt-table-cell-occupancy">Max persons: 2</td>'
        '<td class="hprt-table-cell-price"><span class="prco-valign-middle-helper">VND 1,000,000</span></td>'
        '<td class="hprt-table-cell-conditions">Free cancellation before 9 October 2026 '
        "Total cost to cancel VND 0</td>"
        '<td><select class="hprt-nos-select"><option value="0">0</option><option value="3">3</option>'
        "</select></td></tr></tbody></table>"
    )
    rate = parse_hotel_page(html, "VND", adults=2).offers[0].rates[0]
    assert rate.refundable is True and rate.name == "Free cancellation"


def test_empty_html_is_empty_outcome() -> None:
    page = parse_hotel_page("<html><body></body></html>", expected_currency="VND")
    assert page.outcome == PageOutcome.EMPTY


@pytest.mark.parametrize("name", FIXTURES)
def test_golden(fixtures_dir: Path, name: str) -> None:
    expected_path = fixtures_dir / "html" / f"{name}.expected.json"
    page = parse_hotel_page(_load(fixtures_dir, name), expected_currency="VND", adults=2)
    assert page_to_dict(page) == json.loads(expected_path.read_text(encoding="utf-8"))
