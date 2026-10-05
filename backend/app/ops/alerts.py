from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

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


class EmailAlerter:
    """Ghi log như LogAlerter và gửi email tới operator (OPS_ALERT_EMAILS). Lỗi gửi chỉ ghi log:
    cảnh báo vận hành không được làm hỏng tiến trình đang báo."""

    def __init__(self, sender: "EmailSenderLike", recipients: list[str]) -> None:
        self._sender = sender
        self._recipients = recipients

    async def send(self, text: str) -> None:
        log.warning("ops_alert", text=text)
        from app.notify.render import Email

        first_line = text.splitlines()[0] if text else "ops alert"
        email = Email(
            subject=f"[ScrapeBooking ops] {first_line[:120]}",
            text=text,
            html=f"<pre style='font:14px/1.5 monospace'>{_escape(text)}</pre>",
        )
        for to in self._recipients:
            try:
                await self._sender.send(to, email)
            except Exception:  # noqa: BLE001
                log.exception("ops_alert_email_failed", to=to)


class EmailSenderLike(Protocol):
    @property
    def configured(self) -> bool: ...

    async def send(self, to: str, email: Any) -> None: ...


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_alerter(settings: Any) -> Alerter:
    """EmailAlerter khi có SMTP và OPS_ALERT_EMAILS; không thì LogAlerter."""
    from app.notify.email_sender import SmtpEmailSender

    sender = SmtpEmailSender(settings)
    recipients = settings.ops_alert_email_list
    if sender.configured and recipients:
        return EmailAlerter(sender, recipients)
    return LogAlerter()


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
    if stats.total_probes == 0:
        # Run chốt mà không quét được đêm nào (proxy hỏng, kênh chặn ngay): trước đây im lặng.
        return f"⚠️ Scan run {stats.scan_run_id} collected nothing (0 probes)"
    if stats.success_rate >= threshold:
        return None
    return (
        f"⚠️ Scan run {stats.scan_run_id} success {stats.success_rate:.0%}: "
        f"ok={stats.ok_count} sold_out={stats.sold_out_count} "
        f"blocked={stats.blocked_count} error={stats.error_count} of {stats.total_probes}"
    )
