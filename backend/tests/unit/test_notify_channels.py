"""Cảnh báo đa kênh (D11): gộp sự kiện cùng mốc trên nhiều kênh, đóng bán một kênh, lệch giá kênh."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.notify.alert_rules import EventFact, NightMarket, evaluate_alerts
from app.notify.kinds import NotificationKind as K
from app.notify.kinds import effective_rules
from app.notify.service import merge_channel_events, slot_key

TODAY = date(2026, 10, 1)
NIGHT = date(2026, 10, 3)


def fact(
    event_id: int,
    event_type: str,
    *,
    room: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    delta: str | None = None,
    role: str = "competitor",
) -> EventFact:
    return EventFact(
        event_id=event_id,
        hotel_id=1,
        hotel_name="Caravelle",
        room_type_name=room,
        stay_date=NIGHT,
        event_type=event_type,
        from_value=from_value,
        to_value=to_value,
        delta=Decimal(delta) if delta else None,
        currency="VND",
        role=role,
    )


def test_slot_key_strips_channel_suffix() -> None:
    assert slot_key("t1:2026-10-01T06:00:agoda", "agoda") == "t1:2026-10-01T06:00"
    assert slot_key("t1:2026-10-01T06:00", "booking") == "t1:2026-10-01T06:00"  # run cũ


def test_sold_out_on_two_channels_is_one_item_listing_both() -> None:
    merged = merge_channel_events(
        [("agoda", fact(11, "sold_out")), ("booking", fact(12, "sold_out"))]
    )
    assert len(merged) == 1
    one = merged[0]
    assert one.event_id == 12  # giá trị lấy từ kênh tham chiếu (booking)
    assert one.channels == ("booking", "agoda") and one.open_elsewhere == ()

    items = evaluate_alerts(effective_rules({}), merged, {NIGHT: NightMarket(1, 3)}, TODAY)
    assert len(items) == 1
    assert items[0].headline == "Caravelle hết phòng đêm T7 03/10"
    assert items[0].detail == "1/3 đối thủ đã hết phòng đêm này · trên Booking.com, Agoda"


def test_reference_channel_decides_which_values_are_kept() -> None:
    merged = merge_channel_events(
        [
            ("booking", fact(1, "price_down", from_value="100", to_value="80", delta="-20")),
            ("agoda", fact(2, "price_down", from_value="90", to_value="60", delta="-33.3")),
        ],
        reference_channel="agoda",
    )
    assert [(m.event_id, m.to_value, m.channels) for m in merged] == [
        (2, "60", ("booking", "agoda"))
    ]


def test_sold_out_with_channel_closed_says_closed_not_sold_out() -> None:
    merged = merge_channel_events(
        [
            ("booking", fact(21, "sold_out")),
            ("booking", fact(22, "channel_closed", from_value="agoda,ivivu", to_value="booking")),
            ("agoda", fact(23, "price_down", from_value="100", to_value="80", delta="-20")),
        ]
    )
    # channel_closed chỉ làm rõ sự kiện hết phòng, không thành dòng riêng.
    assert [m.event_type for m in merged] == ["sold_out", "price_down"]
    sold = merged[0]
    assert sold.channels == ("booking",) and sold.open_elsewhere == ("agoda", "ivivu")

    # Không cần ngưỡng min_sold_out: chưa phải hết phòng thật.
    items = evaluate_alerts(effective_rules({}), merged[:1], {}, TODAY)
    assert len(items) == 1
    assert items[0].headline == "Caravelle đóng bán trên Booking.com đêm T7 03/10"
    assert "vẫn bán trên Agoda, iVIVU" in items[0].detail
    assert "chưa chắc hết phòng" in items[0].detail


def test_sold_out_everywhere_has_nothing_open_elsewhere() -> None:
    # booking đóng nhưng agoda (đang báo "vẫn bán") cũng hết trong cùng mốc: là hết phòng thật.
    merged = merge_channel_events(
        [
            ("booking", fact(1, "sold_out")),
            ("booking", fact(2, "channel_closed", from_value="agoda", to_value="booking")),
            ("agoda", fact(3, "sold_out")),
        ]
    )
    assert len(merged) == 1 and merged[0].open_elsewhere == ()


def test_room_level_events_are_not_merged_across_room_types() -> None:
    merged = merge_channel_events(
        [
            ("booking", fact(1, "low_stock_enter", room="Deluxe", to_value="2")),
            ("agoda", fact(2, "low_stock_enter", room="Suite", to_value="1")),
        ]
    )
    assert [(m.room_type_name, m.channels) for m in merged] == [
        ("Deluxe", ("booking",)),
        ("Suite", ("agoda",)),
    ]


def test_own_parity_gap_alert() -> None:
    gap = replace(
        fact(31, "parity_gap", from_value="booking:1000000", to_value="900000", delta="-10.00"),
        role="self",
        hotel_name="Khách sạn của tôi",
        channels=("agoda",),
    )
    items = evaluate_alerts(effective_rules({}), [gap], {}, TODAY)
    assert len(items) == 1 and items[0].kind == K.OWN_PARITY_GAP
    assert items[0].headline == "Khách sạn của tôi đang rẻ hơn 10% trên Agoda đêm T7 03/10"
    assert "Agoda: 900.000 ₫" in items[0].detail and "Booking.com: 1.000.000 ₫" in items[0].detail


def test_own_parity_gap_only_for_own_hotel_and_above_threshold() -> None:
    competitor_gap = fact(1, "parity_gap", from_value="booking:100", to_value="80", delta="-20")
    small = replace(competitor_gap, role="self", delta=Decimal("-4"))
    off = effective_rules({"own_parity_gap": (False, {})})
    assert evaluate_alerts(effective_rules({}), [competitor_gap, small], {}, TODAY) == []
    assert evaluate_alerts(off, [replace(competitor_gap, role="self")], {}, TODAY) == []


def test_parity_gap_keeps_only_cheapest_channel() -> None:
    """Hai run cùng mốc chốt lệch giờ: Booking ghi "rẻ hơn Agoda" trước khi có Mytour, Mytour ghi
    "rẻ hơn Booking" sau. Email chỉ giữ kênh rẻ nhất (Mytour)."""
    from datetime import date
    from decimal import Decimal

    from app.notify.alert_rules import EventFact
    from app.notify.service import merge_channel_events

    def fact(event_id: int, to_value: str, from_value: str) -> EventFact:
        return EventFact(
            event_id=event_id,
            hotel_id=4,
            hotel_name="Rex",
            room_type_name=None,
            stay_date=date(2026, 10, 4),
            event_type="parity_gap",
            from_value=from_value,
            to_value=to_value,
            delta=Decimal("-6.84"),
            currency="VND",
            role="self",
        )

    merged = merge_channel_events(
        [
            ("booking", fact(1, "4058591.00", "agoda:5191221.00")),
            ("mytour", fact(2, "3781000.00", "booking:4058591.00")),
        ]
    )
    assert len(merged) == 1
    assert merged[0].channels == ("mytour",)
    assert merged[0].to_value == "3781000.00"


def test_own_parity_gap_is_grouped_per_hotel_and_channel() -> None:
    """Đại lý bán Rex giá cố định trên Mytour nhiều đêm liền: một dòng "ở N đêm", không N dòng."""
    from datetime import date
    from decimal import Decimal

    from app.notify.alert_rules import EventFact, evaluate_alerts
    from app.notify.kinds import NotificationKind, effective_rules

    def fact(event_id: int, day: int, delta: str, to_value: str) -> EventFact:
        return EventFact(
            event_id=event_id,
            hotel_id=4,
            hotel_name="Rex",
            room_type_name=None,
            stay_date=date(2026, 10, day),
            event_type="parity_gap",
            from_value="booking:4767168.00",
            to_value=to_value,
            delta=Decimal(delta),
            currency="VND",
            channels=("mytour",),
            role="self",
        )

    rules = effective_rules({})
    items = evaluate_alerts(
        rules,
        [
            fact(1, 1, "-20.69", "3781000"),
            fact(2, 2, "-11.07", "3781000"),
            fact(3, 4, "-6.84", "3781000"),
        ],
        {},
        date(2026, 10, 1),
    )
    parity = [it for it in items if it.kind == NotificationKind.OWN_PARITY_GAP]
    assert len(parity) == 1
    assert parity[0].headline == "Rex đang rẻ hơn 7%–21% trên Mytour ở 3 đêm"
    assert parity[0].stay_date == date(2026, 10, 1)
