from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse

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
            subject=f"[OTARadar ops] {first_line[:120]}",
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


def webhook_payload(url: str, text: str) -> dict[str, Any]:
    """Thân JSON theo loại webhook: Discord dùng `content` (≤2000 ký tự); Slack, Google Chat,
    Mattermost, Microsoft Teams (incoming webhook) đều nhận `text`."""
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("discord.com") or host.endswith("discordapp.com"):
        return {"content": text[:1990]}
    return {"text": text[:3900]}


class WebhookAlerter:
    """Gửi cảnh báo vận hành tới webhook chat của đội vận hành (Slack/Discord/Google Chat…).
    Không dùng Telegram: bị chặn ở Việt Nam từ 21/05/2025. Lỗi gửi chỉ ghi log."""

    def __init__(
        self,
        urls: list[str],
        post: "Callable[[str, dict[str, Any]], Awaitable[int]] | None" = None,
        prefix: str = "[OTARadar ops]",
    ) -> None:
        self._urls = urls
        self._post = post or _http_post
        self._prefix = prefix

    async def send(self, text: str) -> None:
        body = f"{self._prefix} {text}" if self._prefix else text
        for url in self._urls:
            try:
                status = await self._post(url, webhook_payload(url, body))
                if status >= 300:
                    log.warning(
                        "ops_alert_webhook_status", status=status, host=urlparse(url).hostname
                    )
            except Exception:  # noqa: BLE001
                log.exception("ops_alert_webhook_failed", host=urlparse(url).hostname)


async def _http_post(url: str, payload: dict[str, Any]) -> int:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload)
    return r.status_code


class CompositeAlerter:
    """Ghi log một lần rồi gửi tới mọi kênh (email, webhook). Một kênh lỗi không chặn kênh khác."""

    def __init__(self, alerters: list[Alerter]) -> None:
        self._alerters = alerters

    async def send(self, text: str) -> None:
        log.warning("ops_alert", text=text)
        for a in self._alerters:
            try:
                await a.send(text)
            except Exception:  # noqa: BLE001
                log.exception("ops_alert_channel_failed", alerter=type(a).__name__)


class _QuietEmailAlerter(EmailAlerter):
    """EmailAlerter không tự ghi log (CompositeAlerter đã ghi)."""

    async def send(self, text: str) -> None:
        from app.notify.render import Email

        first_line = text.splitlines()[0] if text else "ops alert"
        email = Email(
            subject=f"[OTARadar ops] {first_line[:120]}",
            text=text,
            html=f"<pre style='font:14px/1.5 monospace'>{_escape(text)}</pre>",
        )
        for to in self._recipients:
            try:
                await self._sender.send(to, email)
            except Exception:  # noqa: BLE001
                log.exception("ops_alert_email_failed", to=to)


def make_alerter(settings: Any) -> Alerter:
    """Email (SMTP + OPS_ALERT_EMAILS) và/hoặc webhook (OPS_ALERT_WEBHOOK_URLS); không có kênh nào
    thì chỉ ghi log (LogAlerter) — `sb check-ops` báo cấu hình này là thiếu."""
    from app.notify.email_sender import SmtpEmailSender

    channels: list[Alerter] = []
    sender = SmtpEmailSender(settings)
    recipients = settings.ops_alert_email_list
    if sender.configured and recipients:
        channels.append(_QuietEmailAlerter(sender, recipients))
    webhooks = list(getattr(settings, "ops_alert_webhook_url_list", []) or [])
    if webhooks:
        channels.append(WebhookAlerter(webhooks))
    if not channels:
        return LogAlerter()
    return CompositeAlerter(channels)


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
