"""Chỉ số thang phòng trống của thị trường (số thật: Vũng Tàu, chỉ khách sạn, T7 17/10/2026)."""

from decimal import Decimal

from app.marketscan.ladder import (
    hotel_range,
    median_or_none,
    percentile_rank,
    rooms_floor,
    rung_counts,
    sold_out_share,
    tightness,
)

SAT = {"5": {"available": 170}, "10": {"available": 122}, "20": {"available": 79}}


def test_rung_counts_from_base_and_ladder_json() -> None:
    assert rung_counts(208, SAT) == {1: 208, 5: 170, 10: 122, 20: 79}
    assert rung_counts(None, None) == {}
    # Nấc 2 (1 người lớn/phòng) có thể hơn danh sách (2 người lớn) vài khách sạn: kẹp xuống.
    assert rung_counts(100, {"2": {"available": 103}, "3": {"available": 90}}) == {
        1: 100,
        2: 100,
        3: 90,
    }
    assert rung_counts(5, {"x": {"available": 1}, "2": {"available": "?"}}) == {1: 5}


def test_rooms_floor_is_lower_bound_of_rooms_left() -> None:
    # (208−170)·1 + (170−122)·5 + (122−79)·10 + 79·20
    assert rooms_floor({1: 208, 5: 170, 10: 122, 20: 79}) == 2288
    assert rooms_floor({1: 210, 5: 183, 10: 150, 20: 104}) == 2732
    assert rooms_floor({}) is None
    assert rooms_floor({1: 3}) == 3


def test_tightness_and_sold_out_share() -> None:
    assert tightness({1: 208, 10: 122}) == 0.5865
    assert tightness({1: 0, 10: 0}) is None and tightness({1: 10}) is None
    assert sold_out_share(208, 269) == 0.2268
    assert sold_out_share(300, 269) == 0.0  # mẫu số là cận dưới: không âm
    assert sold_out_share(None, 10) is None and sold_out_share(5, 0) is None


def test_hotel_range_from_largest_rung_passed() -> None:
    rungs = (2, 3, 5, 10, 20, 30)
    assert hotel_range(1, rungs) == (1, 1)
    assert hotel_range(5, rungs) == (5, 9)
    assert hotel_range(20, rungs) == (20, 29)
    assert hotel_range(30, rungs) == (30, None)  # qua nấc cao nhất: "≥ 30"
    assert hotel_range(None, rungs) == (None, None)


def test_percentile_rank_and_median() -> None:
    prices = [Decimal(x) for x in (100, 200, 300, 400)]
    assert percentile_rank(prices, Decimal(250)) == 50
    assert percentile_rank(prices, Decimal(400)) == 88  # 3 thấp hơn + nửa của 1 bằng
    assert percentile_rank([], Decimal(1)) is None
    assert median_or_none([0.5, 0.7, 0.9]) == 0.7 and median_or_none([]) is None
