"""Khoảng phòng còn của cả khách sạn (min, max): N chỉ khi biết chắc, còn lại "≥min" / "min–max"."""

import pytest

from app.analytics.rooms_left_bounds import RoomsLeftBounds, definitely_low, hotel_bounds
from app.domain.models import StockConfidence

E, C, H, S = (
    StockConfidence.EXACT,
    StockConfidence.CAPPED,
    StockConfidence.HIDDEN,
    StockConfidence.SOLD_OUT,
)


def test_all_room_types_exact_gives_an_exact_total() -> None:
    b = hotel_bounds([(E, 2), (E, 3), (E, 4)])
    assert b == RoomsLeftBounds(9, 9) and b is not None and b.exact == 9


def test_a_capped_room_type_only_gives_a_floor() -> None:
    # Rex 12/12: 7 loại "≥10" + 1 loại còn 2 → ít nhất 72, không phải "2".
    b = hotel_bounds([(C, 10)] * 7 + [(E, 2)])
    assert b == RoomsLeftBounds(72, None) and b is not None and b.exact is None


def test_hidden_room_type_counts_as_at_least_one() -> None:
    assert hotel_bounds([(E, 2), (H, None)]) == RoomsLeftBounds(3, None)


def test_sold_out_room_type_adds_nothing() -> None:
    assert hotel_bounds([(E, 2), (S, 0)]) == RoomsLeftBounds(2, 2)


def test_calendar_ladder_raises_the_floor_and_sets_the_ceiling() -> None:
    # Reverie 30/10: trang (2 người lớn) Σ = 14 nhưng lịch còn ≥15 → tổng thật khác 14.
    b = hotel_bounds([(E, 4), (E, 2), (E, 4), (E, 3), (E, 1)], calendar_min=15, calendar_max=19)
    assert b == RoomsLeftBounds(15, 19) and b is not None and b.exact is None


def test_calendar_ceiling_bounds_capped_room_types() -> None:
    assert hotel_bounds([(C, 10), (E, 2)], calendar_max=19) == RoomsLeftBounds(12, 19)


def test_calendar_floor_equal_to_ceiling_is_exact() -> None:
    b = hotel_bounds([(C, 10), (E, 4)], calendar_min=14, calendar_max=14)
    assert b is not None and b.exact == 14


def test_ceiling_below_the_page_floor_is_dropped() -> None:
    # Hai nguồn mâu thuẫn (lịch cũ hơn trang): giữ sàn chắc chắn, bỏ trần.
    assert hotel_bounds([(C, 10), (E, 5)], calendar_max=12) == RoomsLeftBounds(15, None)


def test_calendar_floor_above_a_complete_page_drops_the_page_ceiling() -> None:
    assert hotel_bounds([(E, 4), (E, 2)], calendar_min=10) == RoomsLeftBounds(10, None)


def test_sold_out_page_is_exactly_zero() -> None:
    b = hotel_bounds([], sold_out=True)
    assert b == RoomsLeftBounds(0, 0) and b is not None and b.exact == 0


def test_no_room_types_is_unknown() -> None:
    assert hotel_bounds([]) is None


@pytest.mark.parametrize("value", [None, 0])
def test_capped_without_a_value_counts_as_at_least_one(value: int | None) -> None:
    assert hotel_bounds([(C, value)]) == RoomsLeftBounds(1, None)


def test_definitely_low_needs_a_known_ceiling() -> None:
    assert definitely_low(3, 3) and definitely_low(0, 3)
    assert not definitely_low(4, 3)
    # "≥2" (không biết trần) không phải "sắp hết": trước đây ô "2" của Rex (thực ≥72) bị báo thấp.
    assert not definitely_low(None, 3)
