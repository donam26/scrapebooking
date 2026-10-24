"""Tóm tắt "N ngày qua" của một khách sạn từ availability_events (audit F1): đếm theo đêm, không
theo sự kiện, để một biến động không bị tính hai lần (VD 4→1 phòng sinh cả `rooms_decrease` lẫn
`low_stock_enter`) và để nhiều loại phòng cùng đổi giá một đêm chỉ là một đêm.

- Giá: chỉ sự kiện mức khách sạn (giá rẻ nhất cùng phòng, cùng gói); mức loại phòng nhiễu hơn.
- Giảm phòng: chỉ giảm ≥2 phòng hoặc xuống còn ≤3 phòng (bỏ nhiễu ±1 phòng), gộp với
  `low_stock_enter` theo đêm.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.analytics.rules import EventType

ROOMS_DROP_MIN = 2  # giảm ít nhất 2 phòng mới tính
ROOMS_LOW_LEFT = 3  # hoặc xuống còn ≤3 phòng
SOLD_OUT_LIST_MAX = 10

RESTRICTION_TYPES = frozenset(
    {EventType.RESTRICTED, EventType.RESTRICTION_LIFTED, EventType.MIN_STAY_CHANGE}
)


@dataclass(frozen=True)
class EventRow:
    stay_date: date
    event_type: str
    room_type_id: int | None
    from_value: str | None
    to_value: str | None
    delta: Decimal | None


@dataclass
class PriceMove:
    nights: int = 0
    max_pct: Decimal | None = None  # tăng: % lớn nhất (dương); giảm: % giảm sâu nhất (âm)


@dataclass
class HotelEventSummary:
    price_up: PriceMove = field(default_factory=PriceMove)
    price_down: PriceMove = field(default_factory=PriceMove)
    sold_out_nights: list[date] = field(default_factory=list)
    sold_out_total: int = 0
    back_available_nights: int = 0
    promo_on: int = 0
    promo_off: int = 0
    restriction_changes: int = 0
    rooms_drop_nights: int = 0
    total_events: int = 0


def _int(v: str | None) -> int | None:
    try:
        return int(Decimal(v)) if v is not None else None
    except (ArithmeticError, ValueError):
        return None


def _is_rooms_drop(e: EventRow) -> bool:
    if e.event_type == EventType.LOW_STOCK_ENTER:
        return True
    if e.event_type != EventType.ROOMS_DECREASE:
        return False
    before, after = _int(e.from_value), _int(e.to_value)
    if before is None or after is None:
        return False
    return before - after >= ROOMS_DROP_MIN or after <= ROOMS_LOW_LEFT


def summarize_events(events: Iterable[EventRow], today: date) -> HotelEventSummary:
    """`today`: ngày địa phương của tenant; danh sách đêm hết phòng chỉ giữ đêm từ hôm nay."""
    out = HotelEventSummary()
    nights: dict[str, set[date]] = {}
    up: list[Decimal] = []
    down: list[Decimal] = []
    for e in events:
        out.total_events += 1
        kind: str | None = None
        hotel_level = e.room_type_id is None
        if e.event_type == EventType.PRICE_UP and hotel_level:
            kind = "price_up"
            if e.delta is not None:
                up.append(e.delta)
        elif e.event_type == EventType.PRICE_DOWN and hotel_level:
            kind = "price_down"
            if e.delta is not None:
                down.append(e.delta)
        elif e.event_type == EventType.SOLD_OUT:
            kind = "sold_out"
        elif e.event_type == EventType.RESTOCK:
            kind = "restock"
        elif e.event_type == EventType.PROMO_START:
            kind = "promo_on"
        elif e.event_type == EventType.PROMO_END:
            kind = "promo_off"
        elif e.event_type in RESTRICTION_TYPES:
            kind = "restriction"
        elif _is_rooms_drop(e):
            kind = "rooms_drop"
        if kind is not None:
            nights.setdefault(kind, set()).add(e.stay_date)

    def count(kind: str) -> int:
        return len(nights.get(kind, ()))

    out.price_up = PriceMove(count("price_up"), max(up) if up else None)
    out.price_down = PriceMove(count("price_down"), min(down) if down else None)
    upcoming = sorted(d for d in nights.get("sold_out", ()) if d >= today)
    out.sold_out_nights = upcoming[:SOLD_OUT_LIST_MAX]
    out.sold_out_total = len(upcoming)
    out.back_available_nights = count("restock")
    out.promo_on = count("promo_on")
    out.promo_off = count("promo_off")
    out.restriction_changes = count("restriction")
    out.rooms_drop_nights = count("rooms_drop")
    return out
