"""Quy tắc analytics thuần (không I/O): gộp snapshot theo ngày, so sánh với lần quan sát
dùng được gần nhất để sinh sự kiện, và tính chỉ số theo (khách sạn, ngày lưu trú).

Spec mục 7. Mọi ngưỡng đều là tham số.

Roadmap Phase 2 (rate shopping cùng điều kiện, lọc nhiễu):
- "Đổi giá" mức khách sạn chỉ khi gói rẻ nhất ở hai lượt là CÙNG loại phòng, CÙNG khoá gói
  (hoàn huỷ × bữa sáng). Giá thấp nhất đổi vì phòng rẻ nhất hết/mở lại là `lowest_rate_shift`
  (tín hiệu cầu, không phải đổi giá).
- Giá đổi 7 ngày: trung vị % đổi của các cặp (loại phòng, gói) có ở cả hai lần.
- `room_type_gone` chỉ khi vắng ≥2 lượt liên tiếp; `room_type_new` không tính phòng "nhấp nháy".
- Năm trạng thái: còn bán / hết phòng / bị hạn chế (lịch không cho nhận phòng ngày này, hoặc chỉ
  bán từ N>1 đêm) / không có giá / lỗi. Hạn chế không bị tính là hết phòng.
- Giá thành viên (Genius…) không đem so (`loyalty`).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.domain.models import ProbeStatus, StockConfidence


class DateStatus(StrEnum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    # Lịch của kênh không cho nhận phòng ngày này (đóng ngày đến / số đêm tối thiểu không thoả):
    # bán được ở điều kiện khác, không phải hết phòng thật (roadmap 2.7).
    RESTRICTED = "restricted"
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
    # Giá thấp nhất đổi do cơ cấu (phòng/gói rẻ nhất hết hoặc mở lại), không phải đổi giá (2.1).
    LOWEST_RATE_SHIFT = "lowest_rate_shift"
    # Hạn chế bán (2.7, 4.2): lịch không cho nhận phòng ngày này; số đêm tối thiểu đổi.
    RESTRICTED = "restricted"
    RESTRICTION_LIFTED = "restriction_lifted"
    MIN_STAY_CHANGE = "min_stay_change"
    # Radar khuyến mãi (4.1): nhãn KM xuất hiện / biến mất trên các gói công khai.
    PROMO_START = "promo_start"
    PROMO_END = "promo_end"


USABLE = (DateStatus.AVAILABLE, DateStatus.SOLD_OUT)
OBSERVED = (DateStatus.AVAILABLE, DateStatus.SOLD_OUT, DateStatus.RESTRICTED)

_STATUS_BY_PROBE = {
    ProbeStatus.OK: DateStatus.AVAILABLE,
    ProbeStatus.SOLD_OUT: DateStatus.SOLD_OUT,
    ProbeStatus.SKIPPED_CALENDAR: DateStatus.RESTRICTED,
    ProbeStatus.NO_ROOMS_1N: DateStatus.UNKNOWN,
    ProbeStatus.BLOCKED: DateStatus.UNKNOWN,
    ProbeStatus.ERROR: DateStatus.UNKNOWN,
}


def date_status_for_probe(status: str) -> DateStatus:
    return _STATUS_BY_PROBE[ProbeStatus(status)]


# ---- gói giá ---------------------------------------------------------------------------------

ANY_KEY = "*"  # dữ liệu cũ/test không có chi tiết gói: cả loại phòng là một "gói"


def _flag(v: Any) -> str:
    return "t" if v is True else "f" if v is False else "?"


def rate_key(rate: Mapping[str, Any]) -> str:
    """Khoá gói để so cùng điều kiện: hoàn huỷ × bữa sáng ("t|f" = hoàn huỷ, không bữa sáng)."""
    return f"{_flag(rate.get('refundable'))}|{_flag(rate.get('breakfast'))}"


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


@dataclass(frozen=True)
class RatesSummary:
    prices_by_key: dict[str, Decimal]
    min_breakfast_price: Decimal | None
    min_room_only_price: Decimal | None
    promos: dict[
        str, Decimal | None
    ]  # nhãn KM → độ sâu % lớn nhất (so giá gạch), None nếu không rõ
    cheapest: dict[str, Any] | None  # gói công khai rẻ nhất (nhãn KM, giá gạch)


def summarize_rates(rates: Iterable[Mapping[str, Any]]) -> RatesSummary:
    """Tóm tắt các gói công khai của một loại phòng (bỏ giá thành viên `loyalty`)."""
    by_key: dict[str, Decimal] = {}
    bf: Decimal | None = None
    ro: Decimal | None = None
    promos: dict[str, Decimal | None] = {}
    cheapest: dict[str, Any] | None = None
    cheapest_price: Decimal | None = None
    for r in rates:
        if r.get("loyalty") is True:
            continue
        price = _dec(r.get("price"))
        if price is None:
            continue
        k = rate_key(r)
        if k not in by_key or price < by_key[k]:
            by_key[k] = price
        if r.get("breakfast") is True:
            bf = price if bf is None else min(bf, price)
        elif r.get("breakfast") is False:
            ro = price if ro is None else min(ro, price)
        label = (r.get("promo_label") or "").strip()
        if label:
            original = _dec(r.get("price_original"))
            depth = (
                ((original - price) / original * 100).quantize(Decimal("0.1"))
                if original is not None and original > price
                else None
            )
            prev = promos.get(label)
            promos[label] = depth if prev is None or (depth is not None and depth > prev) else prev
        if cheapest_price is None or price < cheapest_price:
            cheapest_price = price
            cheapest = {
                "price": str(price),
                "key": k,
                "refundable": r.get("refundable"),
                "breakfast": r.get("breakfast"),
                "price_original": r.get("price_original"),
                "promo_label": label or None,
                "source_supplier": r.get("source_supplier"),
                "taxes_included": r.get("taxes_included"),
            }
    return RatesSummary(by_key, bf, ro, promos, cheapest)


@dataclass(frozen=True)
class RoomObs:
    room_type_id: int
    rooms_left: int | None
    confidence: StockConfidence
    min_price: Decimal | None
    # Giá thấp nhất trong các gói có huỷ miễn phí (None khi loại phòng không có gói nào như vậy).
    min_refundable_price: Decimal | None = None
    # Giá thấp nhất mỗi khoá gói công khai (hoàn huỷ × bữa sáng); rỗng = không có chi tiết gói.
    prices_by_key: Mapping[str, Decimal] = field(default_factory=dict)
    min_breakfast_price: Decimal | None = None
    min_room_only_price: Decimal | None = None
    promos: Mapping[str, Decimal | None] = field(default_factory=dict)
    cheapest_rate: Mapping[str, Any] | None = None

    @property
    def exact(self) -> bool:
        return self.confidence == StockConfidence.EXACT and self.rooms_left is not None

    @property
    def prices(self) -> Mapping[str, Decimal]:
        if self.prices_by_key:
            return self.prices_by_key
        return {ANY_KEY: self.min_price} if self.min_price is not None else {}


@dataclass(frozen=True)
class Cheapest:
    room_type_id: int
    key: str
    price: Decimal


@dataclass(frozen=True)
class HotelDateObs:
    """Một lần quan sát (hotel, stay_date) ở một scan run."""

    scan_run_id: int
    scanned_at: datetime
    status: DateStatus
    rooms: dict[int, RoomObs] = field(default_factory=dict)  # theo room_type_id
    currency: str | None = None
    # Số đêm đã tìm (số đêm tối thiểu của lịch kênh); >1 = đêm bị hạn chế số đêm.
    min_stay: int = 1
    probe_status: str | None = None

    @property
    def usable(self) -> bool:
        return self.status in USABLE

    @property
    def observed(self) -> bool:
        return self.status in OBSERVED

    @property
    def min_price(self) -> Decimal | None:
        prices = [r.min_price for r in self.rooms.values() if r.min_price is not None]
        return min(prices) if prices else None

    @property
    def min_refundable_price(self) -> Decimal | None:
        prices = [
            r.min_refundable_price
            for r in self.rooms.values()
            if r.min_refundable_price is not None
        ]
        return min(prices) if prices else None

    @property
    def min_breakfast_price(self) -> Decimal | None:
        prices = [r.min_breakfast_price for r in self.rooms.values() if r.min_breakfast_price]
        return min(prices) if prices else None

    @property
    def min_room_only_price(self) -> Decimal | None:
        prices = [r.min_room_only_price for r in self.rooms.values() if r.min_room_only_price]
        return min(prices) if prices else None

    @property
    def exact_rooms_left(self) -> int | None:
        exact = [r.rooms_left for r in self.rooms.values() if r.exact]
        return sum(x for x in exact if x is not None) if exact else None

    @property
    def room_types_available(self) -> int:
        return len(self.rooms)

    def cheapest(self) -> Cheapest | None:
        best: Cheapest | None = None
        for rt, room in self.rooms.items():
            for k, p in room.prices.items():
                if (
                    best is None
                    or p < best.price
                    or (p == best.price and (rt, k) < (best.room_type_id, best.key))
                ):
                    best = Cheapest(rt, k, p)
        return best

    def prices_by_key(self) -> dict[str, Decimal]:
        """Giá thấp nhất mỗi khoá gói trên mọi loại phòng (so cùng điều kiện)."""
        out: dict[str, Decimal] = {}
        for room in self.rooms.values():
            for k, p in room.prices_by_key.items():
                if k not in out or p < out[k]:
                    out[k] = p
        return out

    def promos(self) -> dict[str, Decimal | None]:
        out: dict[str, Decimal | None] = {}
        for room in self.rooms.values():
            for label, depth in room.promos.items():
                prev = out.get(label)
                out[label] = depth if prev is None or (depth is not None and depth > prev) else prev
        return out

    def cheapest_rate(self) -> dict[str, Any] | None:
        c = self.cheapest()
        if c is None:
            return None
        room = self.rooms[c.room_type_id]
        base = dict(room.cheapest_rate or {})
        base.update({"room_type_id": c.room_type_id, "key": c.key, "price": str(c.price)})
        return base


@dataclass(frozen=True)
class EventDraft:
    event_type: EventType
    room_type_id: int | None
    from_value: str | None
    to_value: str | None
    delta: Decimal | None
    confidence: str
    previous_scan_run_id: int | None
    # Lý do/ngữ cảnh (VD lowest_rate_shift: cheapest_gone; khoá gói của đổi giá) và chi tiết.
    reason: str | None = None
    detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class Thresholds:
    low_stock: int = 3
    price_change_pct: Decimal = Decimal("3")


def pct_change(old: Decimal | None, new: Decimal | None) -> Decimal | None:
    if old is None or new is None or old == 0:
        return None
    return ((new - old) / old * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _price_event(
    old: Decimal | None,
    new: Decimal | None,
    room_type_id: int | None,
    prev_run: int,
    thresholds: Thresholds,
    reason: str | None = None,
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
            confidence="exact",
            previous_scan_run_id=prev_run,
            reason=reason,
        )
    ]


def _room_price_events(
    before: RoomObs, room: RoomObs, rt_id: int, prev_run: int, thresholds: Thresholds
) -> list[EventDraft]:
    """Đổi giá của một loại phòng: so CÙNG gói có ở cả hai lần (gói rẻ nhất lần trước)."""
    common = set(before.prices) & set(room.prices)
    if not common:
        return []
    key = min(common, key=lambda k: (before.prices[k], k))
    return _price_event(before.prices[key], room.prices[key], rt_id, prev_run, thresholds, key)


def _hotel_price_events(
    prev: HotelDateObs, cur: HotelDateObs, prev_run: int, thresholds: Thresholds
) -> list[EventDraft]:
    change = pct_change(prev.min_price, cur.min_price)
    if change is None or abs(change) < thresholds.price_change_pct:
        return []
    pc, cc = prev.cheapest(), cur.cheapest()
    if pc is not None and cc is not None and (pc.room_type_id, pc.key) == (cc.room_type_id, cc.key):
        return _price_event(prev.min_price, cur.min_price, None, prev_run, thresholds, cc.key)
    reason = "mix"
    if pc is not None and pc.room_type_id not in cur.rooms:
        reason = "cheapest_gone"
    elif cc is not None and cc.room_type_id not in prev.rooms:
        reason = "cheapest_back"
    elif pc is not None and pc.key not in cur.rooms[pc.room_type_id].prices:
        reason = "rate_gone"
    elif cc is not None and cc.key not in prev.rooms[cc.room_type_id].prices:
        reason = "rate_back"
    return [
        EventDraft(
            EventType.LOWEST_RATE_SHIFT,
            None,
            str(prev.min_price),
            str(cur.min_price),
            change,
            "exact",
            prev_run,
            reason=reason,
        )
    ]


def _promo_events(prev: HotelDateObs, cur: HotelDateObs, prev_run: int) -> list[EventDraft]:
    before, now = prev.promos(), cur.promos()
    out: list[EventDraft] = []
    started = sorted(set(now) - set(before))
    ended = sorted(set(before) - set(now))
    if started:
        depths: list[Decimal] = [d for lb in started if (d := now[lb]) is not None]
        out.append(
            EventDraft(
                EventType.PROMO_START,
                None,
                None,
                ", ".join(started)[:64],
                max(depths) if depths else None,
                "exact",
                prev_run,
                detail={
                    "labels": {lb: str(now[lb]) if now[lb] is not None else None for lb in started}
                },
            )
        )
    if ended:
        out.append(
            EventDraft(
                EventType.PROMO_END,
                None,
                ", ".join(ended)[:64],
                None,
                None,
                "exact",
                prev_run,
                detail={"labels": ended},
            )
        )
    return out


def diff_events(
    prev: HotelDateObs | None,
    cur: HotelDateObs,
    thresholds: Thresholds,
    prev2: HotelDateObs | None = None,
    seen_room_types: frozenset[int] | set[int] | None = None,
) -> list[EventDraft]:
    """Sự kiện giữa lần quan sát dùng được gần nhất (`prev`) và lần hiện tại.

    - Không sinh sự kiện khi hiện tại không quan sát được hoặc không có lần trước.
    - `sold_out` / `restock` / `restricted` / `restriction_lifted` theo chuyển trạng thái.
    - Mức loại phòng chỉ khi cả hai lần đều `available` và cùng số đêm tìm.
    - `prev2` (lần dùng được trước `prev`): chống nhấp nháy loại phòng (2.3).
    - `seen_room_types`: loại phòng đã từng thấy ở đêm này trong cửa sổ lịch sử; loại phòng "mở
      lại" sau khi vắng không phải loại phòng mới (không sinh `room_type_new`).
    """
    if not cur.observed or prev is None or not prev.observed:
        return []
    prev_run = prev.scan_run_id

    def transition(et: EventType) -> list[EventDraft]:
        return [EventDraft(et, None, str(prev.status), str(cur.status), None, "exact", prev_run)]

    if cur.status == DateStatus.RESTRICTED:
        return [] if prev.status == DateStatus.RESTRICTED else transition(EventType.RESTRICTED)
    if prev.status == DateStatus.RESTRICTED:
        # Mở lại sau hạn chế: không so giá/số phòng với lần không bán.
        return (
            transition(EventType.RESTRICTION_LIFTED) if cur.status == DateStatus.AVAILABLE else []
        )
    if prev.status == DateStatus.AVAILABLE and cur.status == DateStatus.SOLD_OUT:
        return transition(EventType.SOLD_OUT)
    if prev.status == DateStatus.SOLD_OUT and cur.status == DateStatus.AVAILABLE:
        # Sau restock không so giá/số phòng với lần hết phòng.
        return transition(EventType.RESTOCK)
    if prev.status == DateStatus.SOLD_OUT and cur.status == DateStatus.SOLD_OUT:
        return []

    events: list[EventDraft] = []
    if prev.min_stay != cur.min_stay:
        events.append(
            EventDraft(
                EventType.MIN_STAY_CHANGE,
                None,
                str(prev.min_stay),
                str(cur.min_stay),
                Decimal(cur.min_stay - prev.min_stay),
                "exact",
                prev_run,
            )
        )
    same_stay = prev.min_stay == cur.min_stay
    # Cả hai đều available: sự kiện mức khách sạn về giá, rồi mức loại phòng.
    if same_stay:
        events.extend(_hotel_price_events(prev, cur, prev_run, thresholds))
        events.extend(_promo_events(prev, cur, prev_run))

    flicker_ok = prev2 is not None and prev2.status == DateStatus.AVAILABLE
    for rt_id, room in cur.rooms.items():
        before = prev.rooms.get(rt_id)
        if before is None:
            # Vắng lần trước nhưng có ở lần trước nữa (nhấp nháy) hoặc đã từng thấy trong lịch sử
            # (mở lại): không phải loại phòng mới.
            seen = seen_room_types is not None and rt_id in seen_room_types
            flicker = flicker_ok and prev2 is not None and rt_id in prev2.rooms
            if not seen and not flicker:
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
        if same_stay:
            events.extend(_room_price_events(before, room, rt_id, prev_run, thresholds))

    # Mất loại phòng: chỉ khi vắng ≥2 lượt liên tiếp (có ở prev2, vắng ở prev và cur).
    if flicker_ok and prev2 is not None:
        for rt_id, before in prev2.rooms.items():
            if rt_id not in prev.rooms and rt_id not in cur.rooms:
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


def last_observed_before(history: Sequence[HotelDateObs], at: datetime) -> HotelDateObs | None:
    """Lần quan sát có trạng thái (còn/hết/hạn chế) gần nhất trước `at` — mốc so sự kiện."""
    candidates = [h for h in history if h.observed and h.scanned_at < at]
    return max(candidates, key=lambda h: h.scanned_at) if candidates else None


def usable_at_or_before(history: Sequence[HotelDateObs], at: datetime) -> HotelDateObs | None:
    """Lần quan sát dùng được gần nhất có scanned_at <= at (dùng cho mốc 24h/72h/7d)."""
    candidates = [h for h in history if h.usable and h.scanned_at <= at]
    return max(candidates, key=lambda h: h.scanned_at) if candidates else None


def paired_exact_pickup(older: HotelDateObs, newer: HotelDateObs) -> int | None:
    """Số phòng còn GIẢM giữa hai lần quan sát (≈ bán thêm, nhưng đóng bán cũng làm giảm), chỉ
    tính loại phòng `exact` ở cả hai lần. Loại phòng có ở lần cũ (exact) nhưng biến mất ở lần mới
    tính là giảm hết số đó."""
    if older.status != DateStatus.AVAILABLE:
        return None
    if newer.status == DateStatus.SOLD_OUT:
        exact_old = [r.rooms_left for r in older.rooms.values() if r.exact]
        return sum(x for x in exact_old if x is not None) if exact_old else None
    if newer.status != DateStatus.AVAILABLE:
        return None
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


def like_for_like_change(older: HotelDateObs, newer: HotelDateObs) -> Decimal | None:
    """Trung vị % đổi giá của các cặp (loại phòng, gói) có ở cả hai lần (2.2): phòng rẻ nhất
    hết không làm "giá tăng"."""
    if older.status != DateStatus.AVAILABLE or newer.status != DateStatus.AVAILABLE:
        return None
    if older.min_stay != newer.min_stay:
        return None
    changes = []
    for rt_id, before in older.rooms.items():
        after = newer.rooms.get(rt_id)
        if after is None:
            continue
        for k, p in before.prices.items():
            q = after.prices.get(k)
            c = pct_change(p, q)
            if c is not None:
                changes.append(c)
    m = median(changes)
    return m.quantize(Decimal("0.01")) if m is not None else None


@dataclass(frozen=True)
class MetricsDraft:
    days_to_arrival: int
    pickup_24h: int | None
    velocity_3d: Decimal | None
    min_price: Decimal | None
    min_refundable_price: Decimal | None
    currency: str | None
    price_change_7d_pct: Decimal | None
    availability_status: DateStatus
    exact_rooms_left: int | None
    exact_share: Decimal | None
    last_observed_at: datetime
    min_breakfast_price: Decimal | None = None
    min_room_only_price: Decimal | None = None
    min_stay: int = 1
    probe_status: str | None = None
    cheapest_rate: dict[str, Any] | None = None
    prices_by_key: dict[str, str] | None = None
    promos: dict[str, str | None] | None = None


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
        if ref7d is not None:
            price_change = like_for_like_change(ref7d, cur)

    window = [h for h in all_obs if h.usable and h.scanned_at >= now - timedelta(days=7)]
    exact_share: Decimal | None = None
    if window:
        n_exact = sum(1 for h in window if h.exact_rooms_left is not None)
        exact_share = (Decimal(n_exact) / Decimal(len(window))).quantize(Decimal("0.0001"))

    priced = cur.status == DateStatus.AVAILABLE
    return MetricsDraft(
        days_to_arrival=stay_date_ordinal_diff,
        pickup_24h=pickup_24h,
        velocity_3d=velocity,
        min_price=cur.min_price if cur.usable else None,
        min_refundable_price=cur.min_refundable_price if cur.usable else None,
        currency=cur.currency if cur.usable else None,
        price_change_7d_pct=price_change,
        availability_status=cur.status,
        exact_rooms_left=cur.exact_rooms_left if cur.usable else None,
        exact_share=exact_share,
        last_observed_at=now,
        min_breakfast_price=cur.min_breakfast_price if priced else None,
        min_room_only_price=cur.min_room_only_price if priced else None,
        min_stay=cur.min_stay,
        probe_status=cur.probe_status,
        cheapest_rate=cur.cheapest_rate() if priced else None,
        prices_by_key={k: str(v) for k, v in cur.prices_by_key().items()} if priced else None,
        promos=(
            {k: str(v) if v is not None else None for k, v in cur.promos().items()}
            if priced
            else None
        ),
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
