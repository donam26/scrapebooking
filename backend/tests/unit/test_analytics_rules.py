from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.rules import (
    DateStatus,
    EventType,
    HotelDateObs,
    RoomObs,
    Thresholds,
    compute_metrics,
    date_status_for_probe,
    diff_events,
    last_usable_before,
    median,
    paired_exact_pickup,
    pct_change,
)
from app.domain.models import StockConfidence as C

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
TH = Thresholds(low_stock=3, price_change_pct=Decimal("3"))


def room(rt: int, left: int | None, conf: C, price: str | None = "100") -> RoomObs:
    return RoomObs(rt, left, conf, Decimal(price) if price else None)


def obs(run: int, at: datetime, status: DateStatus, *rooms: RoomObs) -> HotelDateObs:
    return HotelDateObs(run, at, status, {r.room_type_id: r for r in rooms}, "VND")


def test_probe_status_mapping() -> None:
    assert date_status_for_probe("ok") == DateStatus.AVAILABLE
    assert date_status_for_probe("sold_out") == DateStatus.SOLD_OUT
    assert date_status_for_probe("skipped_calendar") == DateStatus.SOLD_OUT
    for s in ("no_rooms_1n", "blocked", "error"):
        assert date_status_for_probe(s) == DateStatus.UNKNOWN


def test_no_events_without_usable_previous_or_when_current_unknown() -> None:
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, 2, C.EXACT))
    assert diff_events(None, cur, TH) == []
    prev_unknown = obs(1, T0 - timedelta(hours=8), DateStatus.UNKNOWN)
    assert diff_events(prev_unknown, cur, TH) == []
    cur_unknown = obs(2, T0, DateStatus.UNKNOWN)
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 2, C.EXACT))
    assert diff_events(prev, cur_unknown, TH) == []


def test_sold_out_and_restock_transitions() -> None:
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 2, C.EXACT))
    cur = obs(2, T0, DateStatus.SOLD_OUT)
    events = diff_events(prev, cur, TH)
    assert [e.event_type for e in events] == [EventType.SOLD_OUT]
    assert events[0].room_type_id is None and events[0].previous_scan_run_id == 1
    back = obs(3, T0 + timedelta(hours=8), DateStatus.AVAILABLE, room(1, 1, C.EXACT))
    assert [e.event_type for e in diff_events(cur, back, TH)] == [EventType.RESTOCK]
    assert diff_events(cur, obs(3, T0 + timedelta(hours=8), DateStatus.SOLD_OUT), TH) == []


def test_rooms_decrease_only_when_both_exact() -> None:
    prev = obs(
        1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 5, C.EXACT), room(2, 10, C.CAPPED)
    )
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, 4, C.EXACT), room(2, 10, C.CAPPED))
    events = diff_events(prev, cur, TH)
    assert len(events) == 1
    e = events[0]
    assert e.event_type == EventType.ROOMS_DECREASE and e.room_type_id == 1
    assert (e.from_value, e.to_value, e.delta) == ("5", "4", Decimal(-1))
    # capped -> exact: không có rooms_decrease vì lần trước không exact
    prev2 = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 10, C.CAPPED))
    cur2 = obs(2, T0, DateStatus.AVAILABLE, room(1, 5, C.EXACT))
    assert [e.event_type for e in diff_events(prev2, cur2, TH)] == []


def test_rooms_increase() -> None:
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 1, C.EXACT))
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT))
    types = [e.event_type for e in diff_events(prev, cur, TH)]
    assert types == [EventType.ROOMS_INCREASE]


def test_low_stock_enter_once() -> None:
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 10, C.CAPPED))
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT))
    types = [e.event_type for e in diff_events(prev, cur, TH)]
    assert types == [EventType.LOW_STOCK_ENTER]
    nxt = obs(3, T0 + timedelta(hours=8), DateStatus.AVAILABLE, room(1, 2, C.EXACT))
    types = [e.event_type for e in diff_events(cur, nxt, TH)]
    assert types == [EventType.ROOMS_DECREASE]  # đã ở mức thấp, không lặp low_stock_enter


def test_price_events_hotel_and_room_level_with_threshold() -> None:
    prev = obs(
        1,
        T0 - timedelta(hours=8),
        DateStatus.AVAILABLE,
        room(1, None, C.HIDDEN, "100"),
        room(2, None, C.HIDDEN, "200"),
    )
    cur = obs(
        2, T0, DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "102"), room(2, None, C.HIDDEN, "180")
    )
    events = diff_events(prev, cur, TH)
    # hotel min_price 100 -> 102 = +2% (dưới ngưỡng): không có; room 2: 200 -> 180 = -10%
    assert [(e.event_type, e.room_type_id, e.delta) for e in events] == [
        (EventType.PRICE_DOWN, 2, Decimal("-10.00"))
    ]
    cur2 = obs(
        2, T0, DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "110"), room(2, None, C.HIDDEN, "200")
    )
    events = diff_events(prev, cur2, TH)
    assert [(e.event_type, e.room_type_id) for e in events] == [
        (EventType.PRICE_UP, None),
        (EventType.PRICE_UP, 1),
    ]


def test_room_type_new_and_gone() -> None:
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, 2, C.EXACT))
    cur = obs(2, T0, DateStatus.AVAILABLE, room(2, 4, C.EXACT))
    types = sorted(e.event_type for e in diff_events(prev, cur, TH))
    assert types == sorted([EventType.ROOM_TYPE_NEW, EventType.ROOM_TYPE_GONE])


def test_last_usable_before_picks_latest_usable_not_just_previous_run() -> None:
    a = obs(1, T0 - timedelta(hours=16), DateStatus.AVAILABLE, room(1, 5, C.EXACT))
    b = obs(2, T0 - timedelta(hours=8), DateStatus.UNKNOWN)
    assert last_usable_before([b, a], T0) is a
    assert last_usable_before([b], T0) is None


def test_paired_exact_pickup() -> None:
    older = obs(
        1,
        T0 - timedelta(days=1),
        DateStatus.AVAILABLE,
        room(1, 5, C.EXACT),
        room(2, 10, C.CAPPED),
        room(3, 2, C.EXACT),
    )
    newer = obs(2, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT), room(2, 10, C.CAPPED))
    # rt1: 5->3 = 2; rt2 capped: bỏ qua; rt3 biến mất: 2 phòng bán hết
    assert paired_exact_pickup(older, newer) == 4
    assert paired_exact_pickup(older, obs(2, T0, DateStatus.SOLD_OUT)) == 7
    no_exact = obs(1, T0 - timedelta(days=1), DateStatus.AVAILABLE, room(1, 10, C.CAPPED))
    assert paired_exact_pickup(no_exact, newer) is None


def test_compute_metrics_pickup_velocity_price_change_exact_share() -> None:
    h = [
        obs(
            1, T0 - timedelta(days=7, hours=1), DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "100")
        ),
        obs(2, T0 - timedelta(days=3, hours=1), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "105")),
        obs(3, T0 - timedelta(days=1, hours=1), DateStatus.AVAILABLE, room(1, 6, C.EXACT, "108")),
        obs(4, T0 - timedelta(hours=8), DateStatus.UNKNOWN),
    ]
    cur = obs(5, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT, "110"))
    m = compute_metrics(cur, h, stay_date_ordinal_diff=10)
    assert m.days_to_arrival == 10
    assert m.pickup_24h == 3
    assert m.velocity_3d == (Decimal(6) / Decimal(73) * 24).quantize(Decimal("0.001"))
    assert m.price_change_7d_pct == Decimal("10.00")
    assert m.exact_rooms_left == 3 and m.availability_status == DateStatus.AVAILABLE
    # cửa sổ 7 ngày: obs 2, 3 và cur dùng được (obs 1 ngoài cửa sổ, obs 4 unknown) -> 3/3 exact
    assert m.exact_share == Decimal("1.0000")


def test_compute_metrics_unknown_current_keeps_nulls() -> None:
    cur = obs(5, T0, DateStatus.UNKNOWN)
    m = compute_metrics(cur, [], 3)
    assert m.min_price is None and m.pickup_24h is None and m.exact_share is None
    assert m.availability_status == DateStatus.UNKNOWN


def test_pct_change_and_median() -> None:
    assert pct_change(Decimal("100"), Decimal("103")) == Decimal("3.00")
    assert pct_change(None, Decimal("1")) is None
    assert pct_change(Decimal("0"), Decimal("1")) is None
    assert median([]) is None
    assert median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal(2)
    assert median([Decimal(1), Decimal(2)]) == Decimal("1.50")
