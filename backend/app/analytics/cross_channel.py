"""Quy tắc chéo kênh (thuần, D4/D11): so quan sát mới nhất của cùng khách sạn, cùng đêm giữa các
kênh. Không cộng số phòng giữa kênh; chỉ so giá giữa kênh cùng cơ sở giá (cùng tiền tệ; cùng gói
huỷ miễn phí, hoặc cùng đã gồm thuế phí)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.analytics.rules import EventDraft, EventType

# Kênh mà adapter *nhắm* trả giá đã gồm thuế phí, theo phòng/đêm (D3). Chỉ là gợi ý hiển thị
# (API `ChannelDayOut.tax_inclusive`); parity dùng cờ `taxes_included` của từng lần quan sát
# (`rates_tax_inclusive`), vì cùng một kênh có trang gồm thuế, có trang không.
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
    min_refundable_price: Decimal | None = None
    currency: str | None = None
    # Mọi gói giá của lần quan sát đã gồm thuế phí; None = không biết (không đem so giá thấp nhất).
    tax_inclusive: bool | None = None


def rates_tax_inclusive(rates: Sequence[dict[str, Any]]) -> bool | None:
    """Cờ gồm thuế của một lần quan sát từ `room_snapshots.rates`: True khi mọi gói
    `taxes_included=True`, False khi có gói không gồm thuế, None khi không có gói hoặc có gói
    không rõ."""
    if not rates:
        return None
    flags = [r.get("taxes_included") for r in rates]
    if any(f is None for f in flags):
        return None
    return all(f is True for f in flags)


def _fresh(views: list[ChannelView], now: datetime) -> list[ChannelView]:
    return [v for v in views if abs(now - v.observed_at) <= FRESH_FOR]


def channel_closed(
    current: ChannelView, others: list[ChannelView], now: datetime
) -> EventDraft | None:
    """Kênh này vừa hết phòng nhưng kênh khác (quan sát cùng mốc, ≤ `FRESH_FOR` = 3h) vẫn bán:
    nhiều khả năng khách sạn đóng riêng kênh này, không phải hết phòng thật."""
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


def comparable_prices(a: ChannelView, b: ChannelView) -> tuple[Decimal, Decimal] | None:
    """Cặp giá cùng cơ sở của hai kênh: (giá a, giá b). Ưu tiên giá gói huỷ miễn phí khi cả hai
    có; không thì giá thấp nhất, chỉ khi cả hai lần quan sát đã gồm thuế phí. Khác tiền tệ hoặc
    không có cơ sở chung → None."""
    if a.currency is None or b.currency is None or a.currency != b.currency:
        return None
    if a.min_refundable_price is not None and b.min_refundable_price is not None:
        return a.min_refundable_price, b.min_refundable_price
    if a.tax_inclusive and b.tax_inclusive and a.min_price is not None and b.min_price is not None:
        return a.min_price, b.min_price
    return None


def parity_gap(
    current: ChannelView,
    others: list[ChannelView],
    now: datetime,
    threshold_pct: Decimal = Decimal("5"),
) -> EventDraft | None:
    """Giá ở kênh này thấp hơn kênh rẻ nhất còn lại ≥ ngưỡng, so cùng cơ sở (`comparable_prices`).
    `from_value` = "<kênh khác>:<giá>", `to_value` = giá kênh này, `delta` = % chênh (âm)."""
    if current.status != "available":
        return None
    # Kênh "rẻ nhất còn lại" = kênh có % chênh gần 0 nhất (cơ sở so có thể khác nhau theo cặp).
    best: tuple[Decimal, ChannelView, Decimal, Decimal] | None = None
    for other in _fresh(others, now):
        if other.status != "available":
            continue
        pair = comparable_prices(current, other)
        if pair is None or pair[1] <= 0:
            continue
        cur_price, other_price = pair
        gap = ((cur_price - other_price) / other_price * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if best is None or gap > best[0]:
            best = (gap, other, cur_price, other_price)
    if best is None or best[0] > -threshold_pct:
        return None
    gap, other, cur_price, other_price = best
    return EventDraft(
        event_type=EventType.PARITY_GAP,
        room_type_id=None,
        from_value=f"{other.channel}:{other_price}"[:64],
        to_value=str(cur_price),
        delta=gap,
        confidence="exact",
        previous_scan_run_id=None,
    )
