"""Roadmap Phase 2: đổi giá thật vs đổi cơ cấu, cùng điều kiện, hạn chế, KM."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.rules import (
    DateStatus,
    EventType,
    HotelDateObs,
    RoomObs,
    Thresholds,
    compute_metrics,
    diff_events,
    like_for_like_change,
    summarize_rates,
)
from app.domain.models import StockConfidence as C

T0 = datetime(2026, 10, 9, 6, 0, tzinfo=UTC)
TH = Thresholds(low_stock=3, price_change_pct=Decimal("3"))


def room(rt: int, prices: dict[str, str], left: int | None = None) -> RoomObs:
    by_key = {k: Decimal(v) for k, v in prices.items()}
    return RoomObs(
        rt,
        left,
        C.EXACT if left is not None else C.HIDDEN,
        min(by_key.values()),
        None,
        by_key,
    )


def obs(
    run: int,
    at: datetime,
    *rooms: RoomObs,
    status: DateStatus = DateStatus.AVAILABLE,
    min_stay: int = 1,
) -> HotelDateObs:
    return HotelDateObs(run, at, status, {r.room_type_id: r for r in rooms}, "VND", min_stay)


def test_cheapest_room_sold_out_is_lowest_rate_shift_not_price_up() -> None:
    # Phòng rẻ nhất (1) bán hết: giá thấp nhất 100 → 150 nhưng không ai đổi giá (C5).
    prev = obs(1, T0 - timedelta(hours=8), room(1, {"t|f": "100"}), room(2, {"t|f": "150"}))
    cur = obs(2, T0, room(2, {"t|f": "150"}))
    events = diff_events(prev, cur, TH)
    shift = [e for e in events if e.event_type == EventType.LOWEST_RATE_SHIFT]
    assert (
        len(shift) == 1
        and shift[0].reason == "cheapest_gone"
        and shift[0].delta == Decimal("50.00")
    )
    assert not any(e.event_type in (EventType.PRICE_UP, EventType.PRICE_DOWN) for e in events)


def test_same_room_same_rate_is_real_price_change() -> None:
    prev = obs(1, T0 - timedelta(hours=8), room(1, {"t|f": "100", "f|f": "90"}))
    cur = obs(2, T0, room(1, {"t|f": "110", "f|f": "80"}))
    events = diff_events(prev, cur, TH)
    hotel = [e for e in events if e.room_type_id is None]
    assert [(e.event_type, e.reason) for e in hotel] == [(EventType.PRICE_DOWN, "f|f")]
    # Mức loại phòng: so cùng gói rẻ nhất lần trước (f|f 90 → 80).
    roomlevel = [e for e in events if e.room_type_id == 1]
    assert [(e.event_type, e.delta) for e in roomlevel] == [
        (EventType.PRICE_DOWN, Decimal("-11.11"))
    ]


def test_rate_plan_mix_change_is_not_room_price_change() -> None:
    # Gói không hoàn huỷ biến mất: không có gói chung → không có sự kiện giá mức loại phòng.
    prev = obs(1, T0 - timedelta(hours=8), room(1, {"f|f": "90"}))
    cur = obs(2, T0, room(1, {"t|t": "130"}))
    events = diff_events(prev, cur, TH)
    assert [(e.event_type, e.reason) for e in events] == [
        (EventType.LOWEST_RATE_SHIFT, "rate_gone")
    ]


def test_like_for_like_7d_change_ignores_mix() -> None:
    old = obs(1, T0 - timedelta(days=7, hours=1), room(1, {"t|f": "100"}), room(2, {"t|f": "200"}))
    new = obs(2, T0, room(2, {"t|f": "220"}))
    assert like_for_like_change(old, new) == Decimal("10.00")
    m = compute_metrics(new, [old], 7)
    assert m.price_change_7d_pct == Decimal("10.00")  # không phải +120% của giá thấp nhất


def test_restricted_transitions_and_min_stay_change() -> None:
    prev = obs(1, T0 - timedelta(hours=8), room(1, {"t|f": "100"}))
    closed = obs(2, T0, status=DateStatus.RESTRICTED)
    assert [e.event_type for e in diff_events(prev, closed, TH)] == [EventType.RESTRICTED]
    reopened = obs(3, T0 + timedelta(hours=8), room(1, {"t|f": "300"}))
    assert [e.event_type for e in diff_events(closed, reopened, TH)] == [
        EventType.RESTRICTION_LIFTED
    ]
    two_nights = obs(4, T0 + timedelta(hours=16), room(1, {"t|f": "300"}), min_stay=2)
    events = diff_events(prev, two_nights, TH)
    assert [(e.event_type, e.from_value, e.to_value) for e in events] == [
        (EventType.MIN_STAY_CHANGE, "1", "2")
    ]  # không có "+200%" khi số đêm tìm khác nhau


def test_restricted_metrics_have_no_price() -> None:
    m = compute_metrics(obs(1, T0, status=DateStatus.RESTRICTED), [], 3)
    assert m.availability_status == DateStatus.RESTRICTED and m.min_price is None


def test_summarize_rates_skips_loyalty_and_tracks_basis_and_promos() -> None:
    s = summarize_rates(
        [
            {"price": "800", "refundable": False, "breakfast": False, "loyalty": True},
            {
                "price": "1000",
                "refundable": False,
                "breakfast": False,
                "promo_label": "Late Escape Deal",
                "price_original": "2000",
            },
            {"price": "1200", "refundable": True, "breakfast": True},
        ]
    )
    assert s.prices_by_key == {"f|f": Decimal(1000), "t|t": Decimal(1200)}
    assert (s.min_room_only_price, s.min_breakfast_price) == (Decimal(1000), Decimal(1200))
    assert s.promos == {"Late Escape Deal": Decimal("50.0")}
    assert s.cheapest is not None and s.cheapest["promo_label"] == "Late Escape Deal"


def test_promo_start_and_end_events() -> None:
    def r(label: str | None) -> RoomObs:
        return RoomObs(
            1,
            None,
            C.HIDDEN,
            Decimal(100),
            None,
            {"t|f": Decimal(100)},
            promos={label: Decimal(40)} if label else {},
        )

    prev = obs(1, T0 - timedelta(hours=8), r(None))
    cur = obs(2, T0, r("Late Escape Deal"))
    [e] = diff_events(prev, cur, TH)
    assert (e.event_type, e.to_value, e.delta) == (
        EventType.PROMO_START,
        "Late Escape Deal",
        Decimal(40),
    )
    [e] = diff_events(cur, obs(3, T0 + timedelta(hours=8), r(None)), TH)
    assert e.event_type == EventType.PROMO_END
