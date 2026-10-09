"""Roadmap Phase 0: proxy theo sức khoẻ, cảnh báo vận hành, giá nhiều đêm, điều kiện cảnh báo."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.collector.booking.results import probe_result_from_page
from app.collector.proxy import StaticProxyProvider, template_label
from app.domain.models import (
    PageOutcome,
    ParsedPage,
    ProbeMethod,
    RatePlan,
    RoomOffer,
)
from app.ops.alerts import CompositeAlerter, WebhookAlerter, webhook_payload
from app.ops.health_checks import (
    ChannelStats,
    expired_runs_alert,
    stale_channel_alerts,
    success_rate_alerts,
)
from app.ops.proxy_check import ProxyHealth, ProxyHealthStore, all_down, proxy_alert

T1 = "http://u1-{session}:p@gate-a.example.com:7777"
T2 = "http://u2-{session}:p@gate-b.example.com:8888"


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_template_label_hides_credentials() -> None:
    assert template_label(T1, 0) == "#1 gate-a.example.com:7777"
    assert "p@" not in template_label(T2, 1)


def test_provider_skips_tripped_template_then_recovers() -> None:
    clock = FakeClock()
    p = StaticProxyProvider([T1, T2], fail_threshold=2, cooldown_s=60, monotonic=clock)
    a = p.new_endpoint("vn")
    assert a.provider == "#1 gate-a.example.com:7777"
    p.report_failure(a)
    p.report_failure(a)  # ngắt template 1
    picks = {p.new_endpoint("vn").provider for _ in range(4)}
    assert picks == {"#2 gate-b.example.com:8888"}
    clock.t += 61  # hết thời gian ngắt
    picks = {p.new_endpoint("vn").provider for _ in range(4)}
    assert picks == {"#1 gate-a.example.com:7777", "#2 gate-b.example.com:8888"}


def test_provider_success_resets_failures() -> None:
    p = StaticProxyProvider([T1, T2], fail_threshold=2)
    a = p.new_endpoint("vn")
    p.report_failure(a)
    p.report_success(a)
    p.report_failure(a)
    assert p.healthy(a.provider)


def test_provider_shared_down_and_all_down_fallback() -> None:
    p = StaticProxyProvider([T1, T2])
    p.set_shared_down(["#1 gate-a.example.com:7777", "#9 unknown:1"])
    assert {p.new_endpoint("vn").provider for _ in range(3)} == {"#2 gate-b.example.com:8888"}
    # Mọi template đều hỏng: vẫn xoay vòng (không dừng hẳn), scheduler lo hoãn lượt quét.
    p.set_shared_down(p.labels)
    assert len({p.new_endpoint("vn").provider for _ in range(4)}) == 2


def test_proxy_alert_and_all_down() -> None:
    ok = ProxyHealth("#1 a:1", True, "1.2.3.4", 10)
    bad = ProxyHealth("#2 b:2", False, None, 10, "http 407")
    assert not all_down([ok, bad]) and all_down([bad]) and not all_down([])
    assert "deferred" in (proxy_alert([bad]) or "")
    assert "healthy providers" in (proxy_alert([ok, bad]) or "")
    assert proxy_alert([ok]) is None


class FakeRedis:
    def __init__(self) -> None:
        self.h: dict[str, dict[str, str]] = {}

    async def hset(self, name: str, mapping: dict[str, str]) -> None:
        self.h.setdefault(name, {}).update(mapping)

    async def hgetall(self, name: str) -> dict[bytes, bytes]:
        return {k.encode(): v.encode() for k, v in self.h.get(name, {}).items()}

    async def expire(self, name: str, time: int) -> None:
        pass

    async def delete(self, *names: str) -> None:
        for n in names:
            self.h.pop(n, None)


@pytest.mark.asyncio
async def test_proxy_health_store_roundtrip() -> None:
    store = ProxyHealthStore(FakeRedis())
    await store.write(
        [ProxyHealth("#1 a:1", True, "1.1.1.1", 5), ProxyHealth("#2 b:2", False, None, 5, "407")]
    )
    assert await store.down_labels() == {"#2 b:2"}


def test_webhook_payload_by_host() -> None:
    assert webhook_payload("https://discord.com/api/webhooks/1/x", "hi") == {"content": "hi"}
    assert webhook_payload("https://hooks.slack.com/services/x", "hi") == {"text": "hi"}
    assert webhook_payload("https://chat.googleapis.com/v1/spaces/x", "hi") == {"text": "hi"}


@pytest.mark.asyncio
async def test_webhook_and_composite_alerter_isolate_failures() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    async def post(url: str, payload: dict[str, Any]) -> int:
        if "broken" in url:
            raise RuntimeError("down")
        sent.append((url, payload))
        return 200

    hook = WebhookAlerter(["https://broken.example/x", "https://hooks.slack.com/x"], post=post)

    class Boom:
        async def send(self, text: str) -> None:
            raise RuntimeError("smtp down")

    await CompositeAlerter([Boom(), hook]).send("proxy 407")
    assert sent == [("https://hooks.slack.com/x", {"text": "[OTARadar ops] proxy 407"})]


def test_success_rate_alerts_need_samples() -> None:
    assert success_rate_alerts([ChannelStats("booking", 200, 4, 196)]) == []  # 98%
    assert success_rate_alerts([ChannelStats("booking", 10, 10, 0)]) == []  # quá ít mẫu
    alerts = success_rate_alerts([ChannelStats("booking", 300, 210, 90)])  # 30%
    assert [c for c, _ in alerts] == ["booking"] and "30%" in alerts[0][1]


def test_stale_channel_alerts() -> None:
    now = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)
    assert stale_channel_alerts({"booking"}, {"booking": now - timedelta(hours=2)}, now) == []
    out = stale_channel_alerts({"booking"}, {"booking": now - timedelta(hours=14)}, now)
    assert [c for c, _ in out] == ["booking"]
    never = stale_channel_alerts({"booking"}, {}, now)
    assert "ever" in never[0][1]


def test_expired_runs_alert() -> None:
    assert expired_runs_alert([]) is None
    assert "#181" in (expired_runs_alert([181, 185]) or "")


def _offer(price: str, original: str | None = None) -> RoomOffer:
    return RoomOffer(
        external_room_id="1",
        name="Deluxe",
        max_occupancy=2,
        badge_count=None,
        dropdown_max=None,
        rates=(
            RatePlan(
                "Free cancellation",
                Decimal(price),
                "VND",
                True,
                None,
                price_original=Decimal(original) if original else None,
            ),
        ),
    )


def test_booking_multi_night_price_is_normalized_per_night() -> None:
    # Đêm có min-stay 2: Booking hiện tổng 2 đêm (4.000.000) → lưu 2.000.000/đêm (C15).
    page = ParsedPage(PageOutcome.ROOMS, "1", "X", None, (_offer("4000000", "5000001"),))
    kwargs = dict(
        method=ProbeMethod.HTTP,
        checkin=date(2026, 11, 24),
        adults=2,
        raw_html=None,
        http_status=200,
        session_id=None,
        duration_ms=1,
    )
    two = probe_result_from_page(page, nights=2, **kwargs)  # type: ignore[arg-type]
    rate = two.offers[0].rates[0]
    assert (rate.price, rate.price_original) == (Decimal(2000000), Decimal(2500000))
    assert two.offers[0].min_price == Decimal(2000000)
    one = probe_result_from_page(page, nights=1, **kwargs)  # type: ignore[arg-type]
    assert one.offers[0].rates[0].price == Decimal(4000000)


def test_booking_meal_plan_from_text_and_block_id() -> None:
    from app.collector.booking.parser import _breakfast

    assert _breakfast("very good breakfast included free cancellation", "") is True
    assert _breakfast("exceptional breakfast vnd 1,120,000 non-refundable", "") is False
    assert _breakfast("no meals included", "") is False
    assert _breakfast("free cancellation before 9 october", "7433301_243395895_2_0_0") is False
    assert _breakfast("free cancellation", "7433301_243395895_2_1_0") is True
    assert _breakfast("free cancellation", "bbasic_0") is None
