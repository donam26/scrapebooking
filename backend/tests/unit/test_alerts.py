from datetime import UTC, datetime, timedelta

from structlog.testing import capture_logs

from app.clock import FixedClock
from app.ops.alerts import (
    AlertThrottle,
    LogAlerter,
    RunStats,
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


async def test_log_alerter_writes_warning() -> None:
    with capture_logs() as logs:
        await LogAlerter().send("hello")
    assert logs == [{"event": "ops_alert", "text": "hello", "log_level": "warning"}]
