from datetime import date, timedelta
from decimal import Decimal as D

from app.market.occupancy import RoomState, estimate, inventory_from
from app.market.pacing import calibrate, compset_curve, occ_at_lead, pace
from app.market.price_suggest import (
    NightSignals,
    Strategy,
    backtest_verdict,
    reason_text,
    suggest,
)


def test_inventory_uses_max_exact_or_capped_floor() -> None:
    inv = inventory_from(
        [
            RoomState(1, "exact", 4),
            RoomState(1, "exact", 6),
            RoomState(2, "capped", None, 10),
            RoomState(3, "hidden", None),
            RoomState(4, "sold_out", None),
        ]
    )
    assert inv == {1: 6, 2: 10}


def test_estimate_ranges_and_coverage() -> None:
    inv = {1: 6, 2: 10, 3: 4}
    rooms = [RoomState(1, "exact", 2), RoomState(2, "capped", None, 8)]  # loại 3 không bán = 0
    est = estimate("available", rooms, inv)
    assert est is not None
    assert (est.inventory, est.left_low, est.left_high) == (20, 10, 12)
    assert (est.occ_low, est.occ_high, est.occ_mid) == (D("0.4"), D("0.5"), D("0.45"))
    assert est.coverage == D("0.5") and est.reliable  # biết chắc loại 1 và 3: 10/20

    hidden = estimate("available", [RoomState(1, "hidden", None)], {1: 6})
    assert hidden is not None and hidden.coverage == 0 and not hidden.reliable
    assert (hidden.left_low, hidden.left_high) == (1, 6)

    sold = estimate("sold_out", [], inv)
    assert sold is not None and sold.occ_low == sold.occ_high == 1 and sold.coverage == 1
    assert estimate("unknown", rooms, inv) is None
    assert estimate("available", rooms, {}) is None


def test_pace_needs_two_same_weekday_references() -> None:
    night = date(2026, 10, 17)  # thứ Bảy
    curves = {
        night - timedelta(weeks=1): {5: D("0.60")},
        night - timedelta(weeks=2): {6: D("0.40")},  # lệch 1 ngày vẫn dùng
        night - timedelta(weeks=3): {12: D("0.90")},  # quá xa d=5
        night - timedelta(days=1): {5: D("0.99")},  # khác thứ
    }
    p = pace(night, 5, D("0.70"), curves, lambda d: False)
    assert p.references == 2 and p.reference == D("0.50") and p.delta == D("0.2")
    one = pace(night, 5, D("0.70"), {night - timedelta(weeks=1): {5: D("0.6")}}, lambda d: False)
    assert one.reference is None and one.delta is None and one.references == 1
    # đêm lễ chỉ so với đêm lễ
    assert pace(night, 5, D("0.7"), curves, lambda d: d == night).references == 0
    assert occ_at_lead({7: D("0.3")}, 6) == D("0.3") and occ_at_lead({9: D("0.3")}, 6) is None


def test_compset_curve_requires_two_hotels_and_calibration() -> None:
    curve = compset_curve([{5: D("0.2"), 6: D("0.5")}, {5: D("0.6")}, {5: D("0.4")}])
    assert curve == {5: D("0.4")}
    cal = calibrate([(D("0.80"), D("0.70")), (D("0.50"), D("0.60"))])
    assert (cal.nights, cal.mean_abs_error_pts, cal.bias_pts) == (2, D("10.0"), D("0.0"))
    assert calibrate([]).mean_abs_error_pts is None


def night(**kw: object) -> NightSignals:
    base: dict[str, object] = dict(
        stay_date=date(2026, 10, 13),  # thứ Ba
        days_to_arrival=9,
        own_status="available",
        own_price=D("800000"),
        own_rooms_left=None,
        own_occ=None,
        comp_observed=4,
        comp_sold_out=0,
        comp_median_price=D("1000000"),
        comp_occ=None,
        comp_pace=None,
    )
    base.update(kw)
    return NightSignals(**base)  # type: ignore[arg-type]


def test_rms_lite_raise_on_tight_night_is_explained_and_capped() -> None:
    s = suggest(night(comp_sold_out=2, comp_low=1))
    # Tham chiếu 1.000.000 (trung vị × định vị 100), căng 3/4 → +10% = 1.100.000; đổi tối đa 15%
    # so với giá hiện tại 800.000 → 920.000.
    assert s is not None and s.kind == "raise" and s.change_pct == 15
    assert (s.reference_price, s.target_price, s.clamped) == (D(1000000), D(920000), "max_change")
    assert [r.key for r in s.reasons] == ["position", "comp_tight", "clamp_max_change"]
    assert s.reasons[1].pct == 10 and s.confidence == "medium"
    assert reason_text(s.reasons[1], "vi") == "3/4 đối thủ hết hoặc còn ≤3 phòng (+10%)"


def test_rms_lite_positioning_floor_ceiling_and_rounding() -> None:
    st = Strategy(target_index=D(105), ceiling=D(1030000), round_to=10000)
    s = suggest(night(own_price=D("1000000")), st)
    assert s is not None and s.target_price == D(1030000) and s.clamped == "ceiling"
    st2 = Strategy(target_index=D(90), floor=D(950000), target_source="strategy")
    low = suggest(night(own_price=D("1000000")), st2)
    assert low is not None and low.target_price == D(950000) and low.kind == "lower"
    weekend = Strategy(weekday_adj={5: 10})
    sat = suggest(night(stay_date=date(2026, 10, 17), own_price=D("1000000")), weekend)
    assert sat is not None and sat.target_price == D(1100000)
    assert any(r.key == "weekday" and r.pct == 10 for r in sat.reasons)


def test_rms_lite_never_lowers_on_tight_night_or_when_nearly_full() -> None:
    tight = suggest(night(own_price=D("1300000"), comp_sold_out=2))
    assert tight is not None and tight.kind == "hold" and tight.clamped == "no_lower_tight"
    full = suggest(night(own_price=D("1300000"), own_occ=D("0.92"), own_occ_source="otb"))
    assert full is not None and full.kind == "hold" and full.target_price == D(1300000)


def test_rms_lite_last_minute_lower_suggests_promo_and_needs_sample() -> None:
    s = suggest(
        night(own_price=D("1300000"), days_to_arrival=3, own_occ=D("0.4"), own_occ_source="otb")
    )
    assert s is not None and s.kind == "lower" and s.change_pct == -15
    # Chỉ có chỉ báo lấp đầy ước tính, chưa đặt chiến lược: không gợi ý giảm giá.
    est = suggest(night(own_price=D("1300000"), days_to_arrival=3, own_occ=D("0.4")))
    assert est is not None and est.kind == "hold" and est.clamped == "no_lower_without_demand"
    assert [r.key for r in s.restrictions] == ["restrict_open_promo"]
    assert suggest(night(comp_median_price=None, comp_priced=2)) is None
    base = suggest(night(comp_median_price=None, comp_priced=2), Strategy(base_price=D(850000)))
    assert base is not None and base.reasons[0].key == "base_price" and base.confidence == "low"
    assert suggest(night(own_status="sold_out", comp_sold_out=4)) is None


def test_rms_lite_otb_pace_and_min_stay_restriction() -> None:
    fri = night(
        stay_date=date(2026, 10, 23),
        days_to_arrival=14,
        own_price=D("1000000"),
        comp_sold_out=3,
        own_occ=D("0.7"),
        own_occ_source="otb",
        own_pace_4w=15,
        own_capacity=100,
        own_index=D(90),
    )
    s = suggest(fri)
    assert s is not None and any(r.key == "own_pace_ahead" for r in s.reasons)
    assert {r.key for r in s.restrictions} == {"restrict_min_stay", "restrict_stop_discounts"}
    assert s.confidence == "high"
    assert backtest_verdict("raise", D("0.9")) == "good"
    assert backtest_verdict("raise", D("0.5")) == "review"
    assert backtest_verdict("lower", D("0.75")) == "good"
    assert backtest_verdict("hold", D("0.2")) == "neutral"


def test_estimate_rejects_available_without_rooms_and_wide_ranges() -> None:
    # "Còn phòng" nhưng không đọc được loại phòng nào: không suy ra 100%.
    assert estimate("available", [], {1: 6, 2: 10}) is None
    # Biết chắc 50% nhưng khoảng rộng 45 điểm: không đủ tin.
    wide = estimate(
        "available", [RoomState(1, "exact", 0), RoomState(2, "hidden", None)], {1: 10, 2: 10}
    )
    assert wide is not None and wide.coverage == D("0.5")
    assert wide.occ_high - wide.occ_low == D("0.45") and not wide.reliable
