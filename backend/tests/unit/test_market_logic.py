from datetime import date, timedelta
from decimal import Decimal as D

from app.market.occupancy import RoomState, estimate, inventory_from
from app.market.pacing import calibrate, compset_curve, occ_at_lead, pace
from app.market.price_suggest import NightSignals, reason_text, suggest


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
        stay_date=date(2026, 10, 10),
        days_to_arrival=9,
        own_status="available",
        own_price=D("80"),
        own_rooms_left=None,
        own_occ=None,
        comp_observed=4,
        comp_sold_out=0,
        comp_median_price=D("100"),
        comp_occ=None,
        comp_pace=None,
    )
    base.update(kw)
    return NightSignals(**base)  # type: ignore[arg-type]


def test_suggest_raise_when_cheaper_and_market_tight() -> None:
    s = suggest(night(comp_sold_out=2, own_rooms_left=2, holiday="Lễ"))
    assert s is not None and s.kind == "raise" and s.change_pct == 15 and s.confidence == "medium"
    two = suggest(night(comp_sold_out=2, comp_occ=D("0.9")))
    assert two is not None and two.confidence == "high"  # hai tín hiệu căng độc lập
    reasons = [reason_text(r, "vi") for r in s.reasons]
    assert reasons[0] == "2/4 đối thủ đã hết phòng"
    assert "giá bạn thấp hơn trung vị đối thủ 20%" in reasons
    small = suggest(night(own_price=D("95"), comp_pace=D("0.2")))
    assert small is not None and small.change_pct == 5 and small.confidence == "medium"
    assert suggest(night()) is None  # rẻ hơn nhưng thị trường không căng


def test_suggest_hold_and_lower_and_guards() -> None:
    hold = suggest(night(own_price=D("130"), comp_sold_out=2))
    assert hold is not None and hold.kind == "hold" and hold.change_pct == 0
    lower = suggest(night(own_price=D("140"), days_to_arrival=3, own_occ=D("0.4")))
    assert lower is not None and lower.kind == "lower" and lower.change_pct == -10
    assert suggest(night(own_price=D("140"), days_to_arrival=10, own_occ=D("0.4"))) is None
    assert suggest(night(own_status="sold_out", comp_sold_out=4)) is None
    assert suggest(night(comp_observed=1, comp_sold_out=1)) is None


def test_estimate_rejects_available_without_rooms_and_wide_ranges() -> None:
    # "Còn phòng" nhưng không đọc được loại phòng nào: không suy ra 100%.
    assert estimate("available", [], {1: 6, 2: 10}) is None
    # Biết chắc 50% nhưng khoảng rộng 45 điểm: không đủ tin.
    wide = estimate(
        "available", [RoomState(1, "exact", 0), RoomState(2, "hidden", None)], {1: 10, 2: 10}
    )
    assert wide is not None and wide.coverage == D("0.5")
    assert wide.occ_high - wide.occ_low == D("0.45") and not wide.reliable
