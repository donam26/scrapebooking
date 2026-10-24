from datetime import date, timedelta
from decimal import Decimal as D

from app.analytics.event_summary import EventRow, summarize_events

TODAY = date(2026, 10, 24)


def ev(
    day: int,
    kind: str,
    rt: int | None = None,
    a: str | None = None,
    b: str | None = None,
    delta: str | None = None,
) -> EventRow:
    return EventRow(TODAY + timedelta(days=day), kind, rt, a, b, D(delta) if delta else None)


def test_summary_counts_nights_not_events_and_drops_noise() -> None:
    s = summarize_events(
        [
            # Giá: hai loại phòng cùng tăng một đêm + mức khách sạn → 1 đêm; mức loại phòng bỏ qua.
            ev(1, "price_up", None, "100", "120", "20"),
            ev(1, "price_up", 7, "100", "125", "25"),
            ev(2, "price_up", None, "100", "105", "5"),
            ev(3, "price_down", None, "100", "88", "-12"),
            ev(4, "price_down", None, "100", "95", "-5"),
            # Một biến động 4→1: rooms_decrease + low_stock_enter = một đêm giảm phòng.
            ev(5, "rooms_decrease", 7, "4", "1", "-3"),
            ev(5, "low_stock_enter", 7, "4", "1"),
            # Nhiễu ±1 phòng khi còn nhiều phòng: không tính.
            ev(6, "rooms_decrease", 7, "9", "8", "-1"),
            # 4→3: chỉ giảm 1 nhưng xuống ≤3 phòng: tính.
            ev(7, "rooms_decrease", 8, "4", "3", "-1"),
            ev(8, "sold_out"),
            ev(-2, "sold_out"),  # đêm đã qua: không vào danh sách
            ev(8, "restock"),
            ev(9, "promo_start"),
            ev(9, "promo_end"),
            ev(10, "restricted"),
            ev(11, "min_stay_change"),
        ],
        TODAY,
    )
    assert (s.price_up.nights, s.price_up.max_pct) == (2, D("20"))
    assert (s.price_down.nights, s.price_down.max_pct) == (2, D("-12"))
    assert s.rooms_drop_nights == 2
    assert s.sold_out_nights == [TODAY + timedelta(days=8)] and s.sold_out_total == 1
    assert (s.back_available_nights, s.promo_on, s.promo_off) == (1, 1, 1)
    assert s.restriction_changes == 2 and s.total_events == 16


def test_sold_out_list_is_capped_at_ten_sorted() -> None:
    s = summarize_events([ev(d, "sold_out") for d in range(15, 0, -1)], TODAY)
    assert len(s.sold_out_nights) == 10 and s.sold_out_total == 15
    assert s.sold_out_nights == sorted(s.sold_out_nights)
    empty = summarize_events([], TODAY)
    assert empty.price_up.max_pct is None and empty.total_events == 0
