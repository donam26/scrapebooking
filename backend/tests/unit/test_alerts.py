import json
from datetime import UTC, datetime, timedelta

import httpx
import respx

from app.clock import FixedClock
from app.ops.alerts import (
    AlertThrottle,
    RunStats,
    TelegramAlerter,
    block_rate_alert,
    run_summary_alert,
)


def test_block_rate_alert_thresholds() -> None:
    assert block_rate_alert(total=10, blocked=5) is None  # dưới min_total
    assert block_rate_alert(total=100, blocked=10) is None
    msg = block_rate_alert(total=100, blocked=25)
    assert msg is not None and "25%" in msg


def test_run_summary_alert() -> None:
    ok = RunStats(
        scan_run_id=1,
        total_probes=100,
        ok_count=85,
        sold_out_count=10,
        blocked_count=3,
        error_count=2,
    )
    assert run_summary_alert(ok) is None
    bad = RunStats(
        scan_run_id=2,
        total_probes=100,
        ok_count=60,
        sold_out_count=10,
        blocked_count=25,
        error_count=5,
    )
    msg = run_summary_alert(bad)
    assert msg is not None and "run 2" in msg and "70%" in msg


def test_run_summary_alert_empty_run() -> None:
    assert run_summary_alert(RunStats(3, 0, 0, 0, 0, 0)) is None


def test_throttle() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    th = AlertThrottle(clock, min_gap=timedelta(minutes=30))
    assert th.should_send("block_rate") is True
    assert th.should_send("block_rate") is False
    clock.advance(minutes=31)
    assert th.should_send("block_rate") is True
    assert th.should_send("other") is True


@respx.mock
async def test_telegram_sends_message() -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    alerter = TelegramAlerter(token="TOKEN", chat_id="42")
    await alerter.send("hello")
    assert route.called
    body = json.loads(route.calls[0].request.content.decode())
    assert body == {"chat_id": "42", "text": "hello"}


async def test_telegram_disabled_without_token() -> None:
    alerter = TelegramAlerter(token="", chat_id="")
    await alerter.send("ignored")  # không ném lỗi, không gọi mạng
