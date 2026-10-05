"""Quy tắc chéo kênh (D4/D11): đóng bán riêng một kênh, chênh giá giữa kênh cùng cơ sở."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.cross_channel import (
    FRESH_FOR,
    ChannelView,
    channel_closed,
    comparable_prices,
    parity_gap,
    rates_tax_inclusive,
)
from app.analytics.rules import EventType

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def view(
    channel: str,
    status: str,
    price: str | None = None,
    age_h: float = 1,
    *,
    refundable: str | None = None,
    currency: str | None = "VND",
    tax_inclusive: bool | None = True,
) -> ChannelView:
    return ChannelView(
        channel=channel,
        status=status,
        min_price=Decimal(price) if price is not None else None,
        observed_at=NOW - timedelta(hours=age_h),
        min_refundable_price=Decimal(refundable) if refundable is not None else None,
        currency=currency,
        tax_inclusive=tax_inclusive,
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
    # Quan sát của mốc trước (quá FRESH_FOR = 3h) không đủ để kết luận kênh kia còn bán.
    assert FRESH_FOR == timedelta(hours=3)
    assert channel_closed(current, [view("agoda", "available", "1", age_h=4)], NOW) is None
    assert channel_closed(current, [view("agoda", "available", "1", age_h=2.5)], NOW) is not None
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
    # Bên kia hết phòng, không giá, giá 0 hoặc quan sát của mốc trước: không so.
    stale = [
        view("booking", "sold_out"),
        view("ivivu", "available", None),
        view("tripcom", "available", "0"),
        view("booking", "available", "1000", age_h=4),
    ]
    assert parity_gap(view("agoda", "available", "500"), stale, NOW) is None
    assert parity_gap(view("agoda", "sold_out"), others, NOW) is None


def test_parity_gap_min_price_needs_tax_inclusive_on_both_sides() -> None:
    # Cờ gồm thuế theo từng lần quan sát, không theo kênh: trang không gồm thuế (False) hay không
    # rõ (None) ở bất kỳ phía nào đều không đem so giá thấp nhất.
    for flag in (False, None):
        assert (
            parity_gap(
                view("agoda", "available", "500", tax_inclusive=flag),
                [view("booking", "available", "1000")],
                NOW,
            )
            is None
        )
        assert (
            parity_gap(
                view("agoda", "available", "500"),
                [view("booking", "available", "1000", tax_inclusive=flag)],
                NOW,
            )
            is None
        )
    assert (
        parity_gap(view("agoda", "available", "500"), [view("booking", "available", "1000")], NOW)
        is not None
    )


def test_parity_gap_prefers_refundable_basis_when_both_have_it() -> None:
    # Giá thấp nhất chênh 20% (gói không hoàn huỷ rẻ) nhưng gói huỷ miễn phí chỉ chênh 4%: không
    # phải parity gap. Cơ sở huỷ miễn phí không cần cờ thuế.
    cur = view("agoda", "available", "800", refundable="960", tax_inclusive=None)
    other = view("booking", "available", "1000", refundable="1000", tax_inclusive=None)
    assert parity_gap(cur, [other], NOW) is None
    cur2 = view("agoda", "available", "800", refundable="900", tax_inclusive=None)
    ev = parity_gap(cur2, [other], NOW)
    assert ev is not None
    assert (ev.from_value, ev.to_value, ev.delta) == ("booking:1000", "900", Decimal("-10.00"))
    # Một bên không có gói huỷ miễn phí: rơi về giá thấp nhất, cần cả hai gồm thuế.
    no_ref = view("booking", "available", "1000", tax_inclusive=True)
    assert (
        parity_gap(view("agoda", "available", "800", refundable="900"), [no_ref], NOW) is not None
    )
    assert (
        parity_gap(
            view("agoda", "available", "800", refundable="900", tax_inclusive=None), [no_ref], NOW
        )
        is None
    )


def test_parity_gap_picks_closest_other_across_mixed_bases() -> None:
    # booking so theo huỷ miễn phí (-10%), ivivu theo giá thấp nhất (-20%): kênh "rẻ nhất còn lại"
    # là booking (chênh gần 0 nhất) và sự kiện ghi giá theo cơ sở của cặp đó.
    cur = view("agoda", "available", "800", refundable="900")
    booking = view("booking", "available", "950", refundable="1000")
    ivivu = view("ivivu", "available", "1000")
    ev = parity_gap(cur, [booking, ivivu], NOW)
    assert ev is not None
    assert (ev.from_value, ev.to_value, ev.delta) == ("booking:1000", "900", Decimal("-10.00"))
    # Nếu booking chỉ chênh -4% theo huỷ miễn phí thì không có sự kiện dù ivivu chênh -20%.
    booking_close = view("booking", "available", "950", refundable="935")
    assert parity_gap(cur, [booking_close, ivivu], NOW) is None


def test_parity_gap_requires_same_currency() -> None:
    assert (
        parity_gap(
            view("agoda", "available", "40", currency="USD"),
            [view("booking", "available", "1000")],
            NOW,
        )
        is None
    )
    assert (
        parity_gap(
            view("agoda", "available", "500", currency=None),
            [view("booking", "available", "1000")],
            NOW,
        )
        is None
    )
    assert comparable_prices(
        view("agoda", "available", "500", currency="USD"),
        view("booking", "available", "1000", currency="USD"),
    ) == (Decimal("500"), Decimal("1000"))


def test_rates_tax_inclusive_flag_from_snapshot_rates() -> None:
    assert rates_tax_inclusive([]) is None
    assert rates_tax_inclusive([{"taxes_included": True}, {"taxes_included": True}]) is True
    assert rates_tax_inclusive([{"taxes_included": True}, {"taxes_included": False}]) is False
    assert rates_tax_inclusive([{"taxes_included": True}, {"taxes_included": None}]) is None
    assert rates_tax_inclusive([{"price": "1"}]) is None
