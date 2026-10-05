from datetime import date
from decimal import Decimal

import pytest

from app.notify.alert_rules import EventFact, NightMarket, evaluate_alerts
from app.notify.fmt import fmt_money, fmt_night
from app.notify.kinds import (
    InvalidParams,
    effective_rules,
    normalize_params,
)
from app.notify.kinds import (
    NotificationKind as K,
)
from app.notify.render import render_alerts, render_insight

TODAY = date(2026, 10, 1)


def ev(
    event_id: int,
    event_type: str,
    stay: date,
    *,
    hotel: str = "Caravelle",
    hotel_id: int = 1,
    room: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    delta: str | None = None,
) -> EventFact:
    return EventFact(
        event_id,
        hotel_id,
        hotel,
        room,
        stay,
        event_type,
        from_value,
        to_value,
        Decimal(delta) if delta else None,
        "VND",
    )


def rules(**overrides: tuple[bool, dict[str, int]]) -> dict[K, object]:
    return effective_rules({k: v for k, v in overrides.items()})  # type: ignore[return-value]


def test_normalize_params_merges_defaults_and_validates() -> None:
    assert normalize_params(K.COMPETITOR_PRICE_DROP, {"min_pct": 20}) == {
        "within_days": 14,
        "min_pct": 20,
    }
    assert normalize_params(K.DAILY_INSIGHT, None) == {}
    with pytest.raises(InvalidParams):
        normalize_params(K.COMPETITOR_PRICE_DROP, {"min_pct": 1})
    with pytest.raises(InvalidParams):
        normalize_params(K.COMPETITOR_LOW_STOCK, {"min_pct": 10})  # khoá của loại khác
    with pytest.raises(InvalidParams):
        normalize_params(K.COMPETITOR_SOLD_OUT, {"within_days": True})


def test_effective_rules_default_on_and_bad_stored_params_fall_back() -> None:
    r = effective_rules(
        {"competitor_sold_out": (False, {}), "competitor_low_stock": (True, {"within_days": 999})}
    )
    assert all(k in r for k in K)
    assert r[K.COMPETITOR_SOLD_OUT].active is False
    assert r[K.COMPETITOR_LOW_STOCK].params == {"within_days": 7}
    assert r[K.DAILY_INSIGHT].active is True


def test_sold_out_respects_window_level_and_min_sold_out() -> None:
    events = [
        ev(1, "sold_out", date(2026, 10, 3)),
        ev(2, "sold_out", date(2026, 10, 30)),  # ngoài 14 đêm
        ev(3, "sold_out", date(2026, 10, 3), room="Deluxe"),  # mức loại phòng: bỏ
        ev(4, "restock", date(2026, 10, 4)),
    ]
    market = {date(2026, 10, 3): NightMarket(2, 4)}
    items = evaluate_alerts(rules(), events, market, TODAY)
    assert [(i.kind, i.event_id) for i in items] == [(K.COMPETITOR_SOLD_OUT, 1)]
    assert items[0].headline == "Caravelle hết phòng đêm T7 03/10"
    assert items[0].detail == "2/4 đối thủ đã hết phòng đêm này"

    strict = rules(competitor_sold_out=(True, {"within_days": 14, "min_sold_out": 3}))
    assert evaluate_alerts(strict, events, market, TODAY) == []


def test_low_stock_groups_room_types_per_hotel_night() -> None:
    stay = date(2026, 10, 2)
    events = [
        ev(5, "low_stock_enter", stay, room="Suite", to_value="1"),
        ev(6, "low_stock_enter", stay, room="Deluxe King", to_value="2"),
        ev(7, "low_stock_enter", stay, hotel="Park Hyatt", hotel_id=2, room="Twin", to_value="3"),
    ]
    items = evaluate_alerts(rules(), events, {}, TODAY)
    assert [i.hotel_name for i in items] == ["Caravelle", "Park Hyatt"]
    assert items[0].detail == "Deluxe King còn 2 phòng, Suite còn 1 phòng"


def test_price_drop_threshold_and_disabled_rule() -> None:
    stay = date(2026, 10, 5)
    events = [
        ev(8, "price_down", stay, from_value="7200000", to_value="6300000", delta="-12.5"),
        ev(9, "price_down", stay, hotel="Reverie", hotel_id=3, delta="-5"),
        ev(10, "price_down", stay, room="Twin", delta="-30"),  # mức loại phòng: bỏ
    ]
    items = evaluate_alerts(rules(), events, {}, TODAY)
    assert [i.event_id for i in items] == [8]
    assert items[0].headline == "Caravelle giảm giá 12% đêm T2 05/10"
    assert items[0].detail == "giá thấp nhất 7.200.000 ₫ → 6.300.000 ₫"
    off = rules(competitor_price_drop=(False, {}))
    assert evaluate_alerts(off, events, {}, TODAY) == []


def test_render_alerts_subject_escapes_and_hides_technical_ids() -> None:
    stay = date(2026, 10, 3)
    events = [
        ev(1, "sold_out", stay, hotel="<b>Evil</b> & Co"),
        ev(2, "sold_out", stay, hotel="Caravelle", hotel_id=2),
    ]
    items = evaluate_alerts(rules(), events, {stay: NightMarket(2, 3)}, TODAY)
    email = render_alerts("Rex", items, "https://app.example.vn/")
    assert email.subject.endswith("và 1 thay đổi khác")
    assert "<b>Evil</b>" not in email.html and "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in email.html
    assert "https://app.example.vn/hotels/2/dates/2026-10-03" in email.html
    assert "https://app.example.vn/hotels/2/dates/2026-10-03" in email.text
    assert "scan_run" not in email.text and "run_id" not in email.html


def test_render_insight_uses_summary_and_highlights() -> None:
    out = {
        "summary": "Đối thủ kín phòng cuối tuần. Giá của bạn thấp hơn trung vị.",
        "highlights": [{"title": "Cuối tuần căng", "recommendation": "Cân nhắc tăng giá T7"}],
    }
    email = render_insight("Rex", 42, date(2026, 10, 1), out, "http://x")
    assert email.subject == "Bản tin sáng 01/10: Đối thủ kín phòng cuối tuần"
    assert "Cân nhắc tăng giá T7" in email.html and "http://x/insights/42" in email.text


def test_formatters() -> None:
    assert fmt_money(Decimal("4516781.40"), "VND") == "4.516.781 ₫"
    assert fmt_money("120", "USD") == "120 USD"
    assert fmt_night(date(2026, 10, 4)) == "CN 04/10"


def test_sold_out_without_market_counts_only_that_competitor() -> None:
    events = [ev(1, "sold_out", date(2026, 10, 3))]
    assert len(evaluate_alerts(rules(), events, {}, TODAY)) == 1
    two = rules(competitor_sold_out=(True, {"within_days": 14, "min_sold_out": 2}))
    assert evaluate_alerts(two, events, {}, TODAY) == []
