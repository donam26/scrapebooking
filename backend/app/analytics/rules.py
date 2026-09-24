"""Quy tắc analytics thuần (không I/O): gộp snapshot theo ngày, so sánh với lần quan sát
dùng được gần nhất để sinh sự kiện, và tính chỉ số theo (khách sạn, ngày lưu trú).

Spec mục 7. Mọi ngưỡng đều là tham số.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.models import ProbeStatus, StockConfidence


class DateStatus(StrEnum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    SOLD_OUT = "sold_out"
    RESTOCK = "restock"
    ROOMS_DECREASE = "rooms_decrease"
    ROOMS_INCREASE = "rooms_increase"
    LOW_STOCK_ENTER = "low_stock_enter"
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    ROOM_TYPE_NEW = "room_type_new"
    ROOM_TYPE_GONE = "room_type_gone"


USABLE = (DateStatus.AVAILABLE, DateStatus.SOLD_OUT)

_STATUS_BY_PROBE = {
    ProbeStatus.OK: DateStatus.AVAILABLE,
    ProbeStatus.SOLD_OUT: DateStatus.SOLD_OUT,
    ProbeStatus.SKIPPED_CALENDAR: DateStatus.SOLD_OUT,
    ProbeStatus.NO_ROOMS_1N: DateStatus.UNKNOWN,
    ProbeStatus.BLOCKED: DateStatus.UNKNOWN,
    ProbeStatus.ERROR: DateStatus.UNKNOWN,
}


def date_status_for_probe(status: str) -> DateStatus:
    return _STATUS_BY_PROBE[ProbeStatus(status)]


@dataclass(frozen=True)
class RoomObs:
    room_type_id: int
    rooms_left: int | None
    confidence: StockConfidence
    min_price: Decimal | None

    @property
    def exact(self) -> bool:
        return self.confidence == StockConfidence.EXACT and self.rooms_left is not None


@dataclass(frozen=True)
class HotelDateObs:
    """Một lần quan sát (hotel, stay_date) ở một scan run."""

    scan_run_id: int
    scanned_at: datetime
    status: DateStatus
    rooms: dict[int, RoomObs] = field(default_factory=dict)  # theo room_type_id
    currency: str | None = None

    @property
    def usable(self) -> bool:
        return self.status in USABLE

    @property
    def min_price(self) -> Decimal | None:
        prices = [r.min_price for r in self.rooms.values() if r.min_price is not None]
        return min(prices) if prices else None

    @property
    def exact_rooms_left(self) -> int | None:
        exact = [r.rooms_left for r in self.rooms.values() if r.exact]
        return sum(x for x in exact if x is not None) if exact else None

    @property
    def room_types_available(self) -> int:
        return len(self.rooms)


@dataclass(frozen=True)
class EventDraft:
    event_type: EventType
    room_type_id: int | None
    from_value: str | None
    to_value: str | None
    delta: Decimal | None
    confidence: str
    previous_scan_run_id: int | None


@dataclass(frozen=True)
class Thresholds:
    low_stock: int = 3
    price_change_pct: Decimal = Decimal("3")


def pct_change(old: Decimal | None, new: Decimal | None) -> Decimal | None:
    if old is None or new is None or old == 0:
        return None
    return ((new - old) / old * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _price_events(
    old: Decimal | None,
    new: Decimal | None,
    room_type_id: int | None,
    prev_run: int,
    thresholds: Thresholds,
    confidence: str,
) -> list[EventDraft]:
    change = pct_change(old, new)
    if change is None or abs(change) < thresholds.price_change_pct:
        return []
    return [
        EventDraft(
            event_type=EventType.PRICE_UP if change > 0 else EventType.PRICE_DOWN,
            room_type_id=room_type_id,
            from_value=str(old),
            to_value=str(new),
            delta=change,
            confidence=confidence,
            previous_scan_run_id=prev_run,
        )
    ]


def diff_events(
    prev: HotelDateObs | None, cur: HotelDateObs, thresholds: Thresholds
) -> list[EventDraft]:
    """Sự kiện giữa lần quan sát dùng được gần nhất và lần hiện tại.

    - Không sinh sự kiện khi hiện tại là `unknown` hoặc không có lần trước dùng được.
    - `sold_out` / `restock` ở mức khách sạn theo chuyển trạng thái.
    - Mức loại phòng chỉ khi cả hai lần đều `available`.
    """
    if not cur.usable or prev is None or not prev.usable:
        return []
    events: list[EventDraft] = []
    prev_run = prev.scan_run_id

    if prev.status == DateStatus.AVAILABLE and cur.status == DateStatus.SOLD_OUT:
        events.append(
            EventDraft(
                EventType.SOLD_OUT,
                None,
                str(prev.status),
                str(cur.status),
                None,
                "exact",
                prev_run,
            )
        )
        return events
    if prev.status == DateStatus.SOLD_OUT and cur.status == DateStatus.AVAILABLE:
        events.append(
            EventDraft(
                EventType.RESTOCK,
                None,
                str(prev.status),
                str(cur.status),
                None,
                "exact",
                prev_run,
            )
        )
        # Sau restock không so giá/số phòng với lần hết phòng.
        return events
    if prev.status == DateStatus.SOLD_OUT and cur.status == DateStatus.SOLD_OUT:
        return events

    # Cả hai đều available: sự kiện mức khách sạn về giá, rồi mức loại phòng.
    events.extend(_price_events(prev.min_price, cur.min_price, None, prev_run, thresholds, "exact"))

    for rt_id, room in cur.rooms.items():
        before = prev.rooms.get(rt_id)
        if before is None:
            events.append(
                EventDraft(
                    EventType.ROOM_TYPE_NEW,
                    rt_id,
                    None,
                    str(room.rooms_left) if room.rooms_left is not None else None,
                    None,
                    str(room.confidence),
                    prev_run,
                )
            )
            continue
        if before.exact and room.exact:
            assert before.rooms_left is not None and room.rooms_left is not None
            delta = room.rooms_left - before.rooms_left
            if delta != 0:
                events.append(
                    EventDraft(
                        EventType.ROOMS_DECREASE if delta < 0 else EventType.ROOMS_INCREASE,
                        rt_id,
                        str(before.rooms_left),
                        str(room.rooms_left),
                        Decimal(delta),
                        "exact",
                        prev_run,
                    )
                )
        if room.exact and room.rooms_left is not None and room.rooms_left <= thresholds.low_stock:
            was_low = (
                before.exact
                and before.rooms_left is not None
                and before.rooms_left <= thresholds.low_stock
            )
            if not was_low:
                events.append(
                    EventDraft(
                        EventType.LOW_STOCK_ENTER,
                        rt_id,
                        str(before.rooms_left) if before.exact else str(before.confidence),
                        str(room.rooms_left),
                        None,
                        "exact",
                        prev_run,
                    )
                )
        events.extend(
            _price_events(before.min_price, room.min_price, rt_id, prev_run, thresholds, "exact")
        )

    for rt_id, before in prev.rooms.items():
        if rt_id not in cur.rooms:
            events.append(
                EventDraft(
                    EventType.ROOM_TYPE_GONE,
                    rt_id,
                    str(before.rooms_left) if before.rooms_left is not None else None,
                    None,
                    None,
                    str(before.confidence),
                    prev_run,
                )
            )
    return events


def last_usable_before(history: Sequence[HotelDateObs], at: datetime) -> HotelDateObs | None:
    """Lần quan sát dùng được gần nhất trước thời điểm `at`."""
    candidates = [h for h in history if h.usable and h.scanned_at < at]
    return max(candidates, key=lambda h: h.scanned_at) if candidates else None


def usable_at_or_before(history: Sequence[HotelDateObs], at: datetime) -> HotelDateObs | None:
    """Lần quan sát dùng được gần nhất có scanned_at <= at (dùng cho mốc 24h/72h/7d)."""
    candidates = [h for h in history if h.usable and h.scanned_at <= at]
    return max(candidates, key=lambda h: h.scanned_at) if candidates else None


def paired_exact_pickup(older: HotelDateObs, newer: HotelDateObs) -> int | None:
    """Số phòng bán được giữa hai lần quan sát, chỉ tính loại phòng `exact` ở cả hai lần.
    Loại phòng có ở lần cũ (exact) nhưng biến mất ở lần mới tính là bán hết số đó."""
    if older.status != DateStatus.AVAILABLE:
        return None
    if newer.status == DateStatus.SOLD_OUT:
        exact_old = [r.rooms_left for r in older.rooms.values() if r.exact]
        return sum(x for x in exact_old if x is not None) if exact_old else None
    total = 0
    paired = False
    for rt_id, before in older.rooms.items():
        if not before.exact or before.rooms_left is None:
            continue
        after = newer.rooms.get(rt_id)
        if after is None:
            total += before.rooms_left
            paired = True
        elif after.exact and after.rooms_left is not None:
            total += before.rooms_left - after.rooms_left
            paired = True
    return total if paired else None


@dataclass(frozen=True)
class MetricsDraft:
    days_to_arrival: int
    pickup_24h: int | None
    velocity_3d: Decimal | None
    min_price: Decimal | None
    currency: str | None
    price_change_7d_pct: Decimal | None
    availability_status: DateStatus
    exact_rooms_left: int | None
    exact_share: Decimal | None
    last_observed_at: datetime


def compute_metrics(
    cur: HotelDateObs,
    history: Sequence[HotelDateObs],
    stay_date_ordinal_diff: int,
) -> MetricsDraft:
    """Chỉ số cho (hotel, stay_date) tính tại lần quan sát `cur`.

    `history` là các lần quan sát trước (không gồm cur), bất kỳ thứ tự.
    `stay_date_ordinal_diff` = stay_date - ngày của cur.scanned_at.
    """
    now = cur.scanned_at
    all_obs = [*history, cur]

    pickup_24h: int | None = None
    velocity: Decimal | None = None
    price_change: Decimal | None = None
    if cur.usable:
        ref24 = usable_at_or_before(history, now - timedelta(hours=24))
        if ref24 is not None:
            pickup_24h = paired_exact_pickup(ref24, cur)
        ref72 = usable_at_or_before(history, now - timedelta(hours=72))
        if ref72 is not None:
            p = paired_exact_pickup(ref72, cur)
            if p is not None:
                hours = (now - ref72.scanned_at).total_seconds() / 3600
                velocity = (Decimal(p) / Decimal(hours) * 24).quantize(Decimal("0.001"))
        ref7d = usable_at_or_before(history, now - timedelta(days=7))
        if ref7d is not None and ref7d.status == DateStatus.AVAILABLE:
            price_change = pct_change(ref7d.min_price, cur.min_price)

    window = [h for h in all_obs if h.usable and h.scanned_at >= now - timedelta(days=7)]
    exact_share: Decimal | None = None
    if window:
        n_exact = sum(1 for h in window if h.exact_rooms_left is not None)
        exact_share = (Decimal(n_exact) / Decimal(len(window))).quantize(Decimal("0.0001"))

    return MetricsDraft(
        days_to_arrival=stay_date_ordinal_diff,
        pickup_24h=pickup_24h,
        velocity_3d=velocity,
        min_price=cur.min_price if cur.usable else None,
        currency=cur.currency if cur.usable else None,
        price_change_7d_pct=price_change,
        availability_status=cur.status,
        exact_rooms_left=cur.exact_rooms_left if cur.usable else None,
        exact_share=exact_share,
        last_observed_at=now,
    )


def median(values: Iterable[Decimal]) -> Decimal | None:
    xs = sorted(values)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return ((xs[mid - 1] + xs[mid]) / 2).quantize(Decimal("0.01"))
