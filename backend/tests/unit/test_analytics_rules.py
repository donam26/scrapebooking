from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.rules import (
    DateStatus,
    EventType,
    HotelDateObs,
    KnownValues,
    RoomObs,
    Thresholds,
    compute_metrics,
    date_status_for_probe,
    diff_events,
    last_usable_before,
    median,
    paired_exact_pickup,
    pct_change,
    usable_nearest,
)
from app.domain.models import StockConfidence as C

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
TH = Thresholds(low_stock=3, price_change_pct=Decimal("3"))


def room(rt: int, left: int | None, conf: C, price: str | None = "100") -> RoomObs:
    return RoomObs(rt, left, conf, Decimal(price) if price else None)


def obs(
    run: int, at: datetime, status: DateStatus, *rooms: RoomObs, currency: str | None = "VND"
) -> HotelDateObs:
    return HotelDateObs(run, at, status, {r.room_type_id: r for r in rooms}, currency)


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


def test_price_events_require_same_currency() -> None:
    # Proxy trả trang USD: 100 VND -> 5 USD không phải "giảm giá 95%", cả mức khách sạn lẫn loại phòng.
    prev = obs(1, T0 - timedelta(hours=8), DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "100"))
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "5"), currency="USD")
    assert diff_events(prev, cur, TH) == []
    # Cùng tiền tệ thì vẫn sinh sự kiện như cũ.
    same = obs(2, T0, DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "5"))
    assert [e.event_type for e in diff_events(prev, same, TH)] == [
        EventType.PRICE_DOWN,
        EventType.PRICE_DOWN,
    ]
    # Không biết tiền tệ một bên: không so.
    unknown = obs(2, T0, DateStatus.AVAILABLE, room(1, None, C.HIDDEN, "5"), currency=None)
    assert diff_events(prev, unknown, TH) == []


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
    # rt3 có room_type_gone cùng run (kênh/parser bỏ loại phòng): không tính là bán hết 2 phòng.
    assert paired_exact_pickup(older, newer, frozenset({3})) == 2
    # Chỉ loại phòng biến mất mới có gì để bỏ: không còn cặp exact nào -> None.
    only_gone = obs(1, T0 - timedelta(days=1), DateStatus.AVAILABLE, room(3, 2, C.EXACT))
    assert paired_exact_pickup(only_gone, newer, frozenset({3})) is None
    assert paired_exact_pickup(only_gone, newer) == 2


def test_usable_nearest_picks_closest_within_tolerance() -> None:
    target = T0 - timedelta(hours=24)
    far = obs(1, target - timedelta(hours=3), DateStatus.AVAILABLE, room(1, 9, C.EXACT))
    before = obs(2, target - timedelta(minutes=90), DateStatus.AVAILABLE, room(1, 8, C.EXACT))
    after = obs(3, target + timedelta(hours=1), DateStatus.AVAILABLE, room(1, 7, C.EXACT))
    unknown = obs(4, target, DateStatus.UNKNOWN)
    tol = timedelta(hours=2)
    # Gần mốc nhất (sau mốc 1h thắng trước mốc 1h30); unknown không được chọn dù đúng mốc.
    assert usable_nearest([far, before, after, unknown], target, tol) is after
    assert usable_nearest([far, before], target, tol) is before
    # Ngoài dung sai: None (không lấy "≤ mốc" xa 3 giờ).
    assert usable_nearest([far], target, tol) is None
    # Hoà khoảng cách: lấy lần sớm hơn (ổn định).
    tie_a = obs(5, target - timedelta(hours=1), DateStatus.AVAILABLE, room(1, 1, C.EXACT))
    tie_b = obs(6, target + timedelta(hours=1), DateStatus.AVAILABLE, room(1, 1, C.EXACT))
    assert usable_nearest([tie_b, tie_a], target, tol) is tie_a


def test_compute_metrics_reference_windows_have_tolerance() -> None:
    cur = obs(9, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT, "110"))
    # 24h: quan sát 30h trước (ngoài ±2h) không dùng -> pickup None; 25h trước thì dùng.
    h30 = obs(1, T0 - timedelta(hours=30), DateStatus.AVAILABLE, room(1, 6, C.EXACT, "100"))
    assert compute_metrics(cur, [h30], 1).pickup_24h is None
    h25 = obs(2, T0 - timedelta(hours=25), DateStatus.AVAILABLE, room(1, 6, C.EXACT, "100"))
    assert compute_metrics(cur, [h25], 1).pickup_24h == 3
    # 72h: ±4h; 7d: ±12h.
    h77 = obs(3, T0 - timedelta(hours=77), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "100"))
    assert compute_metrics(cur, [h77], 1).velocity_3d is None
    h75 = obs(4, T0 - timedelta(hours=75), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "100"))
    assert compute_metrics(cur, [h75], 1).velocity_3d == (Decimal(6) / Decimal(75) * 24).quantize(
        Decimal("0.001")
    )
    d7_13h = obs(
        5, T0 - timedelta(days=7, hours=13), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "100")
    )
    assert compute_metrics(cur, [d7_13h], 1).price_change_7d_pct is None
    d7_11h = obs(
        6, T0 - timedelta(days=7, hours=11), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "100")
    )
    assert compute_metrics(cur, [d7_11h], 1).price_change_7d_pct == Decimal("10.00")
    # Mốc 7 ngày khác tiền tệ: không có % thay đổi.
    d7_usd = obs(
        7, T0 - timedelta(days=7), DateStatus.AVAILABLE, room(1, 9, C.EXACT, "4"), currency="USD"
    )
    assert compute_metrics(cur, [d7_usd], 1).price_change_7d_pct is None


def test_compute_metrics_pickup_skips_room_types_gone_this_run() -> None:
    ref = obs(
        1, T0 - timedelta(hours=24), DateStatus.AVAILABLE, room(1, 5, C.EXACT), room(2, 4, C.EXACT)
    )
    cur = obs(2, T0, DateStatus.AVAILABLE, room(1, 3, C.EXACT))
    assert compute_metrics(cur, [ref], 1).pickup_24h == 6
    assert compute_metrics(cur, [ref], 1, gone_room_types=frozenset({2})).pickup_24h == 2


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


def test_compute_metrics_unknown_current_without_known_values_keeps_nulls() -> None:
    cur = obs(5, T0, DateStatus.UNKNOWN)
    m = compute_metrics(cur, [], 3)
    assert m.min_price is None and m.pickup_24h is None and m.exact_share is None
    assert m.availability_status == DateStatus.UNKNOWN and m.stale_since is None


def test_compute_metrics_unknown_current_keeps_known_values_and_marks_stale() -> None:
    # Probe bị chặn: giữ giá/số phòng của bản metric hiện có, chỉ đổi trạng thái + stale_since.
    seen_at = T0 - timedelta(hours=8)
    known = KnownValues(Decimal("100"), Decimal("120"), "VND", 4, seen_at)
    m = compute_metrics(obs(5, T0, DateStatus.UNKNOWN), [], 3, known)
    assert (m.min_price, m.min_refundable_price, m.currency, m.exact_rooms_left) == (
        Decimal("100"),
        Decimal("120"),
        "VND",
        4,
    )
    assert m.availability_status == DateStatus.UNKNOWN and m.stale_since == seen_at
    assert m.pickup_24h is None and m.last_observed_at == T0
    # Bản hiện có đã cũ sẵn (lần chặn thứ hai): giữ mốc cũ hơn.
    older = T0 - timedelta(hours=16)
    again = KnownValues(Decimal("100"), None, "VND", 4, seen_at, stale_since=older)
    assert (
        compute_metrics(
            obs(6, T0 + timedelta(hours=8), DateStatus.UNKNOWN), [], 3, again
        ).stale_since
        == older
    )
    # Lần dùng được kế tiếp xoá stale_since và dùng giá mới.
    fresh = compute_metrics(
        obs(7, T0, DateStatus.AVAILABLE, room(1, 2, C.EXACT, "90")), [], 3, again
    )
    assert (
        fresh.stale_since is None
        and fresh.min_price == Decimal("90")
        and fresh.exact_rooms_left == 2
    )
    # Hết phòng (dùng được) không giữ giá cũ.
    sold = compute_metrics(obs(8, T0, DateStatus.SOLD_OUT), [], 3, known)
    assert sold.min_price is None and sold.stale_since is None


def test_pct_change_and_median() -> None:
    assert pct_change(Decimal("100"), Decimal("103")) == Decimal("3.00")
    assert pct_change(None, Decimal("1")) is None
    assert pct_change(Decimal("0"), Decimal("1")) is None
    assert pct_change(Decimal("100"), Decimal("103"), "VND", "VND") == Decimal("3.00")
    assert pct_change(Decimal("100"), Decimal("5"), "VND", "USD") is None
    assert pct_change(Decimal("100"), Decimal("5"), "VND", None) is None
    assert median([]) is None
    assert median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal(2)
    assert median([Decimal(1), Decimal(2)]) == Decimal("1.50")


def test_price_rank_ties_share_rank_and_missing_own_price() -> None:
    from app.analytics.compset import price_rank

    prices = [Decimal("90"), Decimal("100"), Decimal("120")]
    assert price_rank(Decimal("80"), prices) == 1
    assert (
        price_rank(Decimal("100"), prices) == 2
    )  # bằng giá đối thủ 100: cùng hạng, không bị đẩy xuống
    assert price_rank(Decimal("130"), prices) == 4
    assert price_rank(None, prices) is None
    assert price_rank(Decimal("100"), []) == 1


def test_hotel_date_obs_min_refundable_price_ignores_rooms_without_refundable_rate() -> None:
    cur = HotelDateObs(
        scan_run_id=1,
        scanned_at=T0,
        status=DateStatus.AVAILABLE,
        rooms={
            1: RoomObs(1, 2, C.EXACT, Decimal("90"), None),
            2: RoomObs(2, 2, C.EXACT, Decimal("110"), Decimal("130")),
            3: RoomObs(3, 2, C.EXACT, Decimal("100"), Decimal("120")),
        },
    )
    assert cur.min_price == Decimal("90")
    assert cur.min_refundable_price == Decimal("120")
    none = HotelDateObs(1, T0, DateStatus.AVAILABLE, {1: RoomObs(1, 2, C.EXACT, Decimal("90"))})
    assert none.min_refundable_price is None
