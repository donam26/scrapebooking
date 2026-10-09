from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.analytics.compset import CompsetDay
from app.db.models import Tenant
from app.export.csv_tables import _num, events_rows, to_csv
from app.holidays.data import Holiday
from app.notify.render import render_weekly, weekly_sections
from app.notify.service import weekly_due_key
from app.notify.weekly import WeekEvent, build_weekly_report

TODAY = date(2026, 10, 5)  # thứ Hai


def day(d: int, sold: int, observed: int, idx: str | None) -> CompsetDay:
    return CompsetDay(
        stay_date=date(2026, 10, d),
        competitors_observed=observed,
        competitors_sold_out=sold,
        sold_out_share=(Decimal(sold) / Decimal(observed)).quantize(Decimal("0.01"))
        if observed
        else None,
        min_price=None,
        median_price=None,
        currency="VND",
        own_min_price=None,
        own_status=None,
        own_occupancy_pct=None,
        own_rooms_available=None,
        price_index=Decimal(idx) if idx else None,
        own_rank=None,
        priced_hotels=0,
    )


def test_build_weekly_report_counts_tight_nights_and_price_position() -> None:
    events = [
        WeekEvent("Caravelle", "sold_out", False),
        WeekEvent("Caravelle", "price_down", False),
        WeekEvent("Caravelle", "price_down", True),  # mức loại phòng: không đếm giá
        WeekEvent("Park Hyatt", "low_stock_enter", True),
        WeekEvent("Park Hyatt", "restock", False),  # không đếm
    ]
    compset = [day(5, 1, 4, "60"), day(10, 3, 4, "80"), day(11, 2, 4, "45"), day(25, 4, 4, "70")]
    r = build_weekly_report(TODAY, events, compset, [Holiday(date(2026, 10, 10), "Lễ thử", "vn")])
    assert r.counts == {"sold_out": 1, "low_stock_enter": 1, "price_down": 1, "price_up": 0}
    assert r.busiest == ("Caravelle", 3)
    # 25/10 ngoài 14 đêm; xếp theo tỷ lệ hết phòng
    assert r.tight_nights == [(date(2026, 10, 10), 3, 4), (date(2026, 10, 11), 2, 4)]
    assert r.vs_median_avg == -38 and r.vs_median_low == (date(2026, 10, 11), -55)
    assert r.holidays == [(date(2026, 10, 10), "Lễ thử")] and not r.empty

    focus, sections = weekly_sections(r)
    assert focus == "2 đêm tới quá nửa đối thủ hết phòng"
    assert sections[0][1][0] == "Đối thủ hết phòng 1 lần, sắp hết phòng 1 lần, giảm giá 1 lần."
    email = render_weekly("Rex", r, "http://x")
    assert email.subject == "Báo cáo tuần 05/10: 2 đêm tới quá nửa đối thủ hết phòng"
    assert "http://x/overview?days=14" in email.html


def test_weekly_report_empty_without_events_or_data() -> None:
    r = build_weekly_report(TODAY, [], [day(6, 0, 0, None)], [])
    assert r.empty
    assert weekly_sections(r)[0] == "thị trường yên ắng"


def test_weekly_due_key_monday_after_eight_local_time() -> None:
    t = Tenant(id=7, timezone="Asia/Ho_Chi_Minh")
    assert weekly_due_key(t, datetime(2026, 10, 5, 0, 30, tzinfo=UTC)) is None  # 07:30 thứ Hai
    assert weekly_due_key(t, datetime(2026, 10, 5, 1, 5, tzinfo=UTC)) == "weekly:7:2026-W41"


def test_csv_has_bom_escapes_and_plain_numbers() -> None:
    body = to_csv(("a", "b"), [["Rex, Saigon", 'say "hi"']])
    assert body.startswith("﻿a,b\r\n")
    assert '"Rex, Saigon","say ""hi"""' in body
    assert _num(Decimal("4516781.40"), "VND") == "4516781"
    assert _num(Decimal("120.50"), "USD") == "120.5"
    assert _num(None) == ""


def test_events_rows_use_tenant_local_time() -> None:
    from app.api.schemas import EventOut

    e = EventOut(
        id=1,
        hotel_id=2,
        hotel_name="Caravelle Saigon",
        channel="booking",
        room_type_id=None,
        room_type_name=None,
        stay_date=date(2026, 10, 10),
        event_type="sold_out",
        from_value="available",
        to_value="sold_out",
        delta=None,
        confidence="exact",
        previous_scan_run_id=None,
        scan_run_id=3,
        observed_at=datetime(2026, 10, 1, 23, 10, tzinfo=UTC),
    )
    rows = events_rows([e], {2: "Caravelle"}, ZoneInfo("Asia/Ho_Chi_Minh"))
    assert rows == [
        [
            "2026-10-02 06:10",
            "Booking.com",
            "Caravelle",
            "Toàn khách sạn",
            "2026-10-10",
            "Hết phòng",
            "available",
            "sold_out",
            "",
        ]
    ]


def test_csv_text_cells_cannot_start_formulas() -> None:
    from app.export.csv_tables import _text

    assert _text('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert _text("@SUM(A1)") == "'@SUM(A1)" and _text("-1+2") == "'-1+2"
    assert _text("Caravelle") == "Caravelle" and _text(None) == ""


def test_weekly_due_key_tuesday_catch_up_same_iso_week() -> None:
    t = Tenant(id=7, timezone="Asia/Ho_Chi_Minh")
    tuesday = weekly_due_key(t, datetime(2026, 10, 6, 15, 0, tzinfo=UTC))
    assert tuesday == "weekly:7:2026-W41"  # cùng khoá với thứ Hai: không gửi hai lần
    assert weekly_due_key(t, datetime(2026, 10, 7, 1, 0, tzinfo=UTC)) is None  # thứ Tư
