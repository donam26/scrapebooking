"""Quy tắc chéo kênh (thuần, D4/D11): so quan sát mới nhất của cùng khách sạn, cùng đêm giữa các
kênh. Không cộng số phòng giữa kênh; chỉ so giá giữa kênh cùng cơ sở giá (đã gồm thuế phí)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.analytics.rules import EventDraft, EventType

# Kênh mà adapter bảo đảm giá đã gồm thuế phí, theo phòng/đêm, VND (D3). Chỉ các kênh này được đem
# so parity với nhau.
TAX_INCLUSIVE_CHANNELS = frozenset({"booking", "agoda", "ivivu", "tripcom", "mytour"})

# Cùng một mốc quét: các run của mốc chạy lệch nhau tối đa ~90 phút (hạn chót). Quan sát cũ hơn là
# của mốc trước (3 lượt/ngày cách 8h) và không đem so.
FRESH_FOR = timedelta(hours=3)


@dataclass(frozen=True)
class ChannelView:
    """Metric mới nhất của một kênh cho (khách sạn, đêm)."""

    channel: str
    status: str  # available | sold_out | unknown
    min_price: Decimal | None
    observed_at: datetime


def _fresh(views: list[ChannelView], now: datetime) -> list[ChannelView]:
    return [v for v in views if abs(now - v.observed_at) <= FRESH_FOR]


def channel_closed(
    current: ChannelView, others: list[ChannelView], now: datetime
) -> EventDraft | None:
    """Kênh này vừa hết phòng nhưng kênh khác (quan sát ≤12h) vẫn bán: nhiều khả năng khách sạn
    đóng riêng kênh này, không phải hết phòng thật."""
    if current.status != "sold_out":
        return None
    open_elsewhere = sorted(v.channel for v in _fresh(others, now) if v.status == "available")
    if not open_elsewhere:
        return None
    return EventDraft(
        event_type=EventType.CHANNEL_CLOSED,
        room_type_id=None,
        from_value=",".join(open_elsewhere)[:64],
        to_value=current.channel,
        delta=None,
        confidence="exact",
        previous_scan_run_id=None,
    )


def parity_gap(
    current: ChannelView,
    others: list[ChannelView],
    now: datetime,
    threshold_pct: Decimal = Decimal("5"),
) -> EventDraft | None:
    """Giá thấp nhất ở kênh này thấp hơn kênh rẻ nhất còn lại ≥ ngưỡng (cùng cơ sở giá).
    `from_value` = "<kênh khác>:<giá>", `to_value` = giá kênh này, `delta` = % chênh (âm)."""
    if (
        current.status != "available"
        or current.min_price is None
        or current.channel not in TAX_INCLUSIVE_CHANNELS
    ):
        return None
    comparable = [
        v
        for v in _fresh(others, now)
        if v.status == "available"
        and v.min_price is not None
        and v.min_price > 0
        and v.channel in TAX_INCLUSIVE_CHANNELS
    ]
    if not comparable:
        return None
    cheapest = min(comparable, key=lambda v: v.min_price or Decimal(0))
    assert cheapest.min_price is not None
    gap = ((current.min_price - cheapest.min_price) / cheapest.min_price * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if gap > -threshold_pct:
        return None
    return EventDraft(
        event_type=EventType.PARITY_GAP,
        room_type_id=None,
        from_value=f"{cheapest.channel}:{cheapest.min_price}"[:64],
        to_value=str(current.min_price),
        delta=gap,
        confidence="exact",
        previous_scan_run_id=None,
    )
