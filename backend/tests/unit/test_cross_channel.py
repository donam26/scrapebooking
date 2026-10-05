"""Quy tắc chéo kênh (D4/D11): đóng bán riêng một kênh, chênh giá giữa kênh."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.cross_channel import (
    TAX_INCLUSIVE_CHANNELS,
    ChannelView,
    channel_closed,
    parity_gap,
)
from app.analytics.rules import EventType

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def view(channel: str, status: str, price: str | None = None, age_h: float = 1) -> ChannelView:
    return ChannelView(
        channel=channel,
        status=status,
        min_price=Decimal(price) if price is not None else None,
        observed_at=NOW - timedelta(hours=age_h),
    )


def test_channel_closed_when_sold_out_here_but_open_elsewhere() -> None:
    ev = channel_closed(
        view("booking", "sold_out"),
        [view("ivivu", "available", "900"), view("agoda", "available", "1000")],
        NOW,
    )
    assert ev is not None and ev.event_type == EventType.CHANNEL_CLOSED
    assert (ev.from_value, ev.to_value) == ("agoda,ivivu", "booking")
    assert ev.room_type_id is None and ev.confidence == "exact"


def test_channel_closed_needs_fresh_open_channel() -> None:
    current = view("booking", "sold_out")
    assert channel_closed(current, [], NOW) is None
    assert channel_closed(current, [view("agoda", "sold_out")], NOW) is None
    assert channel_closed(current, [view("agoda", "unknown")], NOW) is None
    # Quan sát quá 12 giờ không đủ để kết luận kênh kia còn bán.
    assert channel_closed(current, [view("agoda", "available", "1", age_h=13)], NOW) is None
    assert (
        channel_closed(view("booking", "available", "1"), [view("agoda", "available")], NOW) is None
    )


def test_parity_gap_when_cheaper_than_cheapest_other_channel() -> None:
    ev = parity_gap(
        view("agoda", "available", "900"),
        [view("booking", "available", "1000"), view("ivivu", "available", "1100")],
        NOW,
    )
    assert ev is not None and ev.event_type == EventType.PARITY_GAP
    assert (ev.from_value, ev.to_value, ev.delta) == ("booking:1000", "900", Decimal("-10.00"))


def test_parity_gap_threshold_and_comparability() -> None:
    others = [view("booking", "available", "1000")]
    assert parity_gap(view("agoda", "available", "960"), others, NOW) is None  # -4% < ngưỡng 5%
    assert parity_gap(view("agoda", "available", "950"), others, NOW) is not None  # đúng -5%
    assert parity_gap(view("agoda", "available", "1100"), others, NOW) is None  # đắt hơn
    assert (
        parity_gap(view("agoda", "available", "960"), others, NOW, threshold_pct=Decimal("3"))
        is not None
    )
    # Kênh chưa bảo đảm giá gồm thuế (cơ sở giá khác) không đem so, cả hai phía.
    assert parity_gap(view("expedia", "available", "500"), others, NOW) is None
    assert (
        parity_gap(view("agoda", "available", "500"), [view("expedia", "available", "1000")], NOW)
        is None
    )
    # Bên kia hết phòng, không giá, giá 0 hoặc quan sát cũ: không so.
    stale = [
        view("booking", "sold_out"),
        view("ivivu", "available", None),
        view("tripcom", "available", "0"),
        view("booking", "available", "1000", age_h=13),
    ]
    assert parity_gap(view("agoda", "available", "500"), stale, NOW) is None
    assert parity_gap(view("agoda", "sold_out"), others, NOW) is None


def test_tax_inclusive_channels() -> None:
    # Adapter của các kênh này bảo đảm giá đã gồm thuế phí (D3); kênh khác không đem so giá.
    assert TAX_INCLUSIVE_CHANNELS == {"booking", "agoda", "ivivu", "tripcom", "mytour"}
    assert "expedia" not in TAX_INCLUSIVE_CHANNELS and "traveloka" not in TAX_INCLUSIVE_CHANNELS
