from datetime import UTC, datetime, timedelta

import pytest
import structlog
from structlog.testing import capture_logs

import app.ops.alerts as alerts_module
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
    # Run chốt mà không thu được probe nào (proxy hỏng, kênh chặn từ đầu) là sự cố cần báo.
    msg = run_summary_alert(RunStats(3, 0, 0, 0, 0, 0))
    assert msg is not None and "run 3" in msg and "0 probes" in msg


async def test_throttle() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    th = AlertThrottle(clock, min_gap=timedelta(minutes=30))
    assert await th.should_send("block_rate") is True
    assert await th.should_send("block_rate") is False
    clock.advance(minutes=31)
    assert await th.should_send("block_rate") is True
    assert await th.should_send("other") is True


class FakeRedis:
    """SET NX EX tối giản; `fail` = Redis lỗi (throttle phải rơi về bộ nhớ, không nuốt cảnh báo)."""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, tuple[str, int | None]] = {}
        self.fail = fail

    async def set(
        self, key: str, value: str, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if self.fail:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = (value, ex)
        return True


async def test_throttle_uses_redis_set_nx_ex_shared_between_processes() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    redis = FakeRedis()
    gap = timedelta(minutes=30)
    a, b = AlertThrottle(clock, gap, redis=redis), AlertThrottle(clock, gap, redis=redis)
    assert await a.should_send("proxy") is True
    assert await b.should_send("proxy") is False  # tiến trình/bản sao khác thấy cùng khoá
    assert redis.store == {"alert_throttle:proxy": ("1", 1800)}
    assert await b.should_send("block_rate:agoda") is True


async def test_throttle_falls_back_to_memory_when_redis_fails() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    th = AlertThrottle(clock, timedelta(minutes=30), redis=FakeRedis(fail=True))
    assert await th.should_send("proxy") is True
    assert await th.should_send("proxy") is False


async def test_log_alerter_writes_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    # Logger của module có thể đã được structlog cache (cache_logger_on_first_use) với danh sách
    # processors cũ nếu test trước gọi configure_logging() lần nữa (app lifespan); capture_logs
    # chỉ sửa danh sách hiện tại, nên dùng một proxy mới chưa cache.
    monkeypatch.setattr(alerts_module, "log", structlog.get_logger("app.ops.alerts"))
    with capture_logs() as logs:
        await LogAlerter().send("hello")
    assert logs == [{"event": "ops_alert", "text": "hello", "log_level": "warning"}]
