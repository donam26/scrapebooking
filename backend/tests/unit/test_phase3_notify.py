"""Roadmap Phase 3: loại cảnh báo mới, kênh gửi Zalo/webhook, giờ im lặng."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.notify.alert_rules import EventFact, NightMarket, evaluate_alerts
from app.notify.channels import (
    Message,
    WebhookNotifier,
    ZaloZnsNotifier,
    normalize_vn_phone,
    parse_templates,
)
from app.notify.kinds import NotificationKind as K
from app.notify.kinds import effective_rules
from app.notify.service import in_quiet_hours, subscription_matches

TODAY = date(2026, 10, 9)
NIGHT = date(2026, 10, 17)


def ev(
    eid: int,
    et: str,
    *,
    role: str = "competitor",
    hotel_id: int = 2,
    delta: str | None = None,
    to_value: str | None = None,
    from_value: str | None = None,
    stay: date = NIGHT,
    reason: str | None = None,
    detail: dict[str, Any] | None = None,
) -> EventFact:
    return EventFact(
        eid,
        hotel_id,
        "Caravelle" if role == "competitor" else "Rex",
        None,
        stay,
        et,
        from_value,
        to_value,
        Decimal(delta) if delta else None,
        "VND",
        role=role,
        reason=reason,
        detail=detail,
    )


def only(*kinds: K) -> dict[K, Any]:
    return effective_rules({str(k): (k in kinds, {}) for k in K})


def test_market_tight_when_share_reached_and_run_touched_night() -> None:
    market = {NIGHT: NightMarket(2, 4, low=1, price_index=Decimal(92), sample="ok", priced=2)}
    items = evaluate_alerts(only(K.MARKET_TIGHT), [ev(1, "sold_out")], market, TODAY)
    assert [i.kind for i in items] == [K.MARKET_TIGHT]
    assert "3/4" in items[0].detail and "92" in items[0].detail  # rẻ hơn khi căng: gợi ý tăng
    # Dưới ngưỡng 50% hoặc chưa đủ 3 đối thủ quan sát: không báo.
    calm = {NIGHT: NightMarket(1, 4)}
    assert evaluate_alerts(only(K.MARKET_TIGHT), [ev(1, "sold_out")], calm, TODAY) == []
    few = {NIGHT: NightMarket(2, 2)}
    assert evaluate_alerts(only(K.MARKET_TIGHT), [ev(1, "sold_out")], few, TODAY) == []


def test_competitor_price_rise_uses_real_hotel_level_change() -> None:
    events = [ev(1, "price_up", delta="12.5", from_value="1000000", to_value="1125000")]
    [item] = evaluate_alerts(only(K.COMPETITOR_PRICE_RISE), events, {}, TODAY)
    assert "tăng giá 12%" in item.headline and "1.125.000" in item.detail
    # lowest_rate_shift (phòng rẻ nhất hết) không phải tăng giá.
    shift = [ev(2, "lowest_rate_shift", delta="40")]
    assert evaluate_alerts(only(K.COMPETITOR_PRICE_RISE), shift, {}, TODAY) == []


def test_competitor_promo_groups_nights() -> None:
    events = [
        ev(1, "promo_start", delta="40", to_value="Late Escape Deal", stay=NIGHT),
        ev(2, "promo_start", delta="35", to_value="Late Escape Deal", stay=date(2026, 10, 18)),
        ev(3, "promo_start", delta="5", to_value="Small", stay=NIGHT),
    ]
    [item] = evaluate_alerts(only(K.COMPETITOR_PROMO), events, {}, TODAY)
    assert "Late Escape Deal" in item.headline and "40" in item.headline
    assert "2" in item.detail


def test_own_position_drift_against_target() -> None:
    market = {NIGHT: NightMarket(0, 5, price_index=Decimal(118), sample="ok", priced=5)}
    events = [ev(1, "price_up", role="self", hotel_id=1, delta="8")]
    [item] = evaluate_alerts(
        only(K.OWN_POSITION_DRIFT), events, market, TODAY, target_index=Decimal(105)
    )
    assert "13" in item.headline and "118" in item.detail and "105" in item.detail
    insufficient = {NIGHT: NightMarket(0, 2, price_index=Decimal(150), sample="insufficient")}
    assert evaluate_alerts(only(K.OWN_POSITION_DRIFT), events, insufficient, TODAY) == []


def test_own_closed_on_channel() -> None:
    events = [ev(1, "restricted", role="self", hotel_id=1)]
    [item] = evaluate_alerts(only(K.OWN_CLOSED), events, {}, TODAY, locale="en")
    assert "Booking.com" in item.headline and "arrivals" in item.headline


def test_quiet_hours_wrap_midnight_and_subscription_kinds() -> None:
    late = datetime(2026, 10, 9, 23, 30, tzinfo=UTC)
    early = datetime(2026, 10, 9, 6, 59, tzinfo=UTC)
    noon = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    assert in_quiet_hours(late, "22:00", "07:00") and in_quiet_hours(early, "22:00", "07:00")
    assert not in_quiet_hours(noon, "22:00", "07:00")
    assert in_quiet_hours(noon, "12:00", "13:00") and not in_quiet_hours(noon, None, "07:00")
    assert subscription_matches([], "alerts") and subscription_matches(["alerts"], "alerts")
    assert not subscription_matches(["daily_insight"], "alerts")
    assert subscription_matches(["daily_insight"], "test")


def test_phone_and_templates() -> None:
    assert normalize_vn_phone("0912 345 678") == "84912345678"
    assert normalize_vn_phone("+84 912-345-678") == "84912345678"
    assert normalize_vn_phone("12345") is None
    assert parse_templates("alerts=1, daily_insight = 2,bad") == {
        "alerts": "1",
        "daily_insight": "2",
    }


MSG = Message(
    "alerts",
    "Đêm T7 17/10 đang căng",
    "3/4 đối thủ hết",
    2,
    "09/10/2026",
    "https://x/a",
    "https://x/r",
)


@pytest.mark.asyncio
async def test_zalo_zns_payload_and_cost() -> None:
    calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def post(
        url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        calls.append((url, body, headers))
        return 200, {"error": 0, "message": "Success", "data": {"msg_id": "m1"}}

    z = ZaloZnsNotifier("tok", {"alerts": "321"}, Decimal(250), post=post)
    assert z.configured
    res = await z.send("0912345678", MSG, "trk")
    assert (res.external_id, res.cost_vnd) == ("m1", Decimal(250))
    url, body, headers = calls[0]
    assert body["phone"] == "84912345678" and body["template_id"] == "321"
    assert body["tracking_id"] == "trk" and body["template_data"]["url"] == "https://x/a"
    assert headers["access_token"] == "tok"


@pytest.mark.asyncio
async def test_zalo_error_and_refresh_token() -> None:
    async def post(
        url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        assert headers["access_token"] == "fresh"
        return 200, {"error": -124, "message": "Template invalid"}

    async def form(
        url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        assert headers["secret_key"] == "sec" and body["grant_type"] == "refresh_token"
        return 200, {"access_token": "fresh", "refresh_token": "r2", "expires_in": 90000}

    z = ZaloZnsNotifier(
        "",
        {"default": "9"},
        app_id="a",
        app_secret="sec",
        refresh_token="r1",
        post=post,
        form_post=form,
    )
    assert z.configured
    with pytest.raises(RuntimeError, match="-124"):
        await z.send("0912345678", MSG, "trk")
    assert not ZaloZnsNotifier("", {"alerts": "1"}).configured


@pytest.mark.asyncio
async def test_webhook_notifier_formats_by_host() -> None:
    sent: list[dict[str, Any]] = []

    async def post(
        url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        sent.append(body)
        return 200, {}

    await WebhookNotifier(post=post).send("https://discord.com/api/webhooks/x", MSG, "t")
    assert "content" in sent[0] and "https://x/a" in sent[0]["content"]
