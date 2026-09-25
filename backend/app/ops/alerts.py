from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.clock import Clock
from app.logging import get_logger

log = get_logger(__name__)


class Alerter(Protocol):
    async def send(self, text: str) -> None: ...


class NullAlerter:
    async def send(self, text: str) -> None:
        log.info("alert_suppressed", text=text)


class LogAlerter:
    """Cảnh báo vận hành ghi thành log warning (event `ops_alert`) để lọc trong log tập trung."""

    async def send(self, text: str) -> None:
        log.warning("ops_alert", text=text)


class AlertThrottle:
    def __init__(self, clock: Clock, min_gap: timedelta) -> None:
        self._clock = clock
        self._gap = min_gap
        self._last: dict[str, datetime] = {}

    def should_send(self, key: str) -> bool:
        now = self._clock.now()
        last = self._last.get(key)
        if last is not None and now - last < self._gap:
            return False
        self._last[key] = now
        return True


def block_rate_alert(
    total: int, blocked: int, min_total: int = 20, threshold: float = 0.2
) -> str | None:
    if total < min_total:
        return None
    rate = blocked / total
    if rate <= threshold:
        return None
    return f"⚠️ Block rate {rate:.0%} ({blocked}/{total} probes) in the last 15 minutes"


@dataclass(frozen=True)
class RunStats:
    scan_run_id: int
    total_probes: int
    ok_count: int
    sold_out_count: int
    blocked_count: int
    error_count: int

    @property
    def success_rate(self) -> float:
        if self.total_probes == 0:
            return 0.0
        return (self.ok_count + self.sold_out_count) / self.total_probes


def run_summary_alert(stats: RunStats, threshold: float = 0.9) -> str | None:
    if stats.total_probes == 0 or stats.success_rate >= threshold:
        return None
    return (
        f"⚠️ Scan run {stats.scan_run_id} success {stats.success_rate:.0%}: "
        f"ok={stats.ok_count} sold_out={stats.sold_out_count} "
        f"blocked={stats.blocked_count} error={stats.error_count} of {stats.total_probes}"
    )
