"""Thang nbRooms (hàm thuần): mỗi nấc N là một request lịch cho mọi đêm cần đo."""

from datetime import date

from app.worker.capacity_ladder import Ladder

D1, D2, D3 = date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 30)


def test_rungs_at_or_below_the_page_floor_are_skipped() -> None:
    ladder = Ladder({D1: 14, D2: 90})
    assert ladder.needs(10) == []  # sàn 14 đã ≥ 10
    assert ladder.needs(15) == [D1]
    assert ladder.needs(100) == [D1, D2]
    assert Ladder({D2: 90}).needs(80) == []


def test_available_raises_the_floor_and_unavailable_sets_the_ceiling() -> None:
    # Reverie 30/10 live: trang Σ = 14, lịch còn ở 15, hết ở 50.
    ladder = Ladder({D1: 14, D3: 14})
    ladder.apply(15, {D1: False, D3: True})
    assert ladder.bounds() == {D1: (None, 14), D3: (15, None)}
    assert ladder.needs(20) == [D3]
    ladder.apply(20, {D3: False})
    assert ladder.bounds() == {D1: (None, 14), D3: (15, 19)}
    assert ladder.needs(25) == []


def test_missing_days_in_the_calendar_answer_change_nothing() -> None:
    ladder = Ladder({D1: 3})
    ladder.apply(5, {})
    assert ladder.bounds() == {} and ladder.needs(5) == [D1]


def test_bounds_only_lists_measured_nights() -> None:
    ladder = Ladder({D1: 3, D2: 4})
    ladder.apply(5, {D1: True})
    assert ladder.bounds() == {D1: (5, None)}


def test_low_rungs_pin_an_exact_low_stock_night() -> None:
    """Trang: còn đúng 2. Nấc 3 hết → trần 2: cả khách sạn còn chính xác 2 (không thành "2–4")."""
    from app.analytics.rooms_left_bounds import hotel_bounds
    from app.domain.models import StockConfidence

    ladder = Ladder({D1: 2})
    assert ladder.needs(2) == [] and ladder.needs(3) == [D1]
    ladder.apply(3, {D1: False})
    lo, hi = ladder.bounds()[D1]
    b = hotel_bounds([(StockConfidence.EXACT, 2)], calendar_min=lo, calendar_max=hi)
    assert b is not None and b.exact == 2
