"""NotificationService: quyết định gửi gì, cho ai, và gửi đúng một lần.

Outbox: mỗi email có `dedupe_key` duy nhất (`alerts:{tenant}:{run}`, `insight:{id}`, …). Dòng được
chèn ở trạng thái "sending" và commit trước khi gửi (ON CONFLICT DO NOTHING), nên cron chạy lại,
worker khởi động lại hay analytics chạy lại đều không chèn trùng. Thử lại giành dòng bằng UPDATE có
điều kiện (chỉ một tiến trình thắng), chờ tăng dần giữa các lần (RETRY_BACKOFF). Lỗi của một tenant
được ghi log và bỏ qua, không chặn tenant khác.

Không gửi bù: thông báo bị "skipped" (chưa cấu hình SMTP, chưa có người nhận) là trạng thái cuối,
vì cảnh báo về đối thủ chỉ có giá trị khi kịp thời.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from html import escape, unescape
from typing import Any, Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.config import Settings
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateSnapshot,
    Insight,
    Listing,
    Notification,
    NotificationDelivery,
    NotificationRecipient,
    NotificationRule,
    NotificationSubscription,
    Probe,
    RoomType,
    ScanRun,
    Tenant,
    TenantHotel,
)
from app.holidays.data import holidays_between
from app.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.logging import get_logger
from app.notify.alert_rules import AlertItem, EventFact, NightMarket, evaluate_alerts
from app.notify.channels import Message, Notifier, build_notifiers
from app.notify.email_sender import EmailSender
from app.notify.kinds import ALERT_KINDS, NotificationKind, RuleConfig, effective_rules
from app.notify.render import (
    Email,
    render_alerts,
    render_insight,
    render_stale,
    render_test,
    render_weekly,
)
from app.notify.weekly import COUNTED, OUTLOOK_NIGHTS, WeekEvent, build_weekly_report
from app.ops.health_checks import channel_last_success, stale_after_hours
from app.repo.runs import MARKET_RUN_PREFIX

log = get_logger(__name__)

ROW_ALERTS = "alerts"
ROW_TEST = "test"
# Chờ sau lần gửi lỗi thứ 1, 2, 3 trước khi thử lại; tổng cộng tối đa 4 lần trong khoảng 2,5 giờ.
RETRY_BACKOFF = (timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2))
MAX_ATTEMPTS = len(RETRY_BACKOFF) + 1
LOOKBACK = timedelta(hours=24)
# Thời gian chờ analytics của mọi kênh trong một mốc trước khi gửi email với phần đã có.
ANALYTICS_GRACE = timedelta(hours=2)
INSIGHT_LOOKBACK = timedelta(hours=36)
SENDING_STALE = timedelta(minutes=10)  # "sending" lâu hơn thế = worker chết giữa chừng
TEST_COOLDOWN = timedelta(seconds=60)
SUBJECT_MAX = 300  # độ dài cột notifications.subject

# Lý do "skipped" (mã máy, dashboard dịch sang lời của chủ khách sạn).
SKIP_NO_MATCHES = "no_matches"
SKIP_NO_RECIPIENTS = "no_recipients"
SKIP_NOT_CONFIGURED = "smtp_not_configured"
SKIP_DISABLED = "disabled"
ROW_STALE = "data_stale"
# Kênh ngoài email: mỗi (khoá outbox, kênh) một dòng riêng, chỉ khi tenant có người đăng ký kênh đó.
FANOUT_CHANNELS = ("zalo", "webhook")


class TestTooSoon(Exception):
    pass


@dataclass
class DispatchReport:
    alerts: int = 0
    insights: int = 0
    weekly: int = 0
    retried: int = 0
    stale: int = 0


class _HasTimezone(Protocol):
    @property
    def timezone(self) -> str: ...


@dataclass(frozen=True)
class TenantInfo:
    """Bản chụp giá trị của tenant: an toàn sau rollback (đối tượng ORM bị expire)."""

    id: int
    name: str
    timezone: str
    country_code: str
    language: str = DEFAULT_LOCALE  # ngôn ngữ báo cáo (`insight_language`): chữ của mọi email

    @classmethod
    def of(cls, t: Tenant) -> "TenantInfo":
        return cls(
            t.id,
            t.name,
            t.timezone,
            t.country_code,
            normalize_locale(t.insight_language),
        )


WEEKLY_HOUR = 8  # thứ Hai, giờ địa phương của tenant


def slot_key(trigger_key: str, channel: str) -> str:
    """Mốc quét của run: bỏ hậu tố ":<kênh>" (khoá run có dạng "<mốc>:booking")."""
    suffix = f":{channel}"
    return trigger_key[: -len(suffix)] if trigger_key.endswith(suffix) else trigger_key


def tenant_now(tenant: _HasTimezone, now: datetime) -> datetime:
    try:
        tz = ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return now.astimezone(tz)


def tenant_today(tenant: _HasTimezone, now: datetime) -> date:
    return tenant_now(tenant, now).date()


def weekly_due_key(tenant: Any, now: datetime) -> str | None:
    """Khoá báo cáo tuần khi tenant đang ở thứ Hai từ WEEKLY_HOUR (hoặc thứ Ba, để bù nếu worker
    tắt cả thứ Hai) theo giờ địa phương; cùng tuần ISO nên không gửi hai lần."""
    local = tenant_now(tenant, now)
    if not ((local.weekday() == 0 and local.hour >= WEEKLY_HOUR) or local.weekday() == 1):
        return None
    year, week, _ = local.isocalendar()
    return f"weekly:{tenant.id}:{year}-W{week:02d}"


def in_quiet_hours(local: datetime, start: str | None, end: str | None) -> bool:
    """Giờ im lặng [start, end) theo giờ tenant, có thể qua nửa đêm ("22:00"–"07:00")."""
    if not start or not end:
        return False
    try:
        a = int(start[:2]) * 60 + int(start[3:5])
        b = int(end[:2]) * 60 + int(end[3:5])
    except ValueError:
        return False
    m = local.hour * 60 + local.minute
    return a <= m < b if a < b else (m >= a or m < b)


def subscription_matches(kinds: list[str] | None, kind: str) -> bool:
    return kind == ROW_TEST or not kinds or kind in kinds


def _new_token() -> str:
    import secrets

    return secrets.token_urlsafe(24)


class NotificationService:
    def __init__(
        self,
        session: AsyncSession,
        sender: EmailSender,
        settings: Settings,
        notifiers: dict[str, Notifier] | None = None,
    ) -> None:
        self._s = session
        self._sender = sender
        self._base_url = settings.app_base_url
        self._notifiers = notifiers if notifiers is not None else build_notifiers(settings)

    # ---- cấu hình theo tenant -------------------------------------------------

    async def rules(self, tenant_id: int) -> dict[NotificationKind, RuleConfig]:
        rows = await self._s.execute(
            select(NotificationRule.kind, NotificationRule.active, NotificationRule.params).where(
                NotificationRule.tenant_id == tenant_id
            )
        )
        return effective_rules({r[0]: (r[1], r[2]) for r in rows})

    async def recipients(self, tenant_id: int) -> list[str]:
        rows = await self._s.execute(
            select(NotificationRecipient.email)
            .where(
                NotificationRecipient.tenant_id == tenant_id,
                NotificationRecipient.active.is_(True),
            )
            .order_by(NotificationRecipient.id)
        )
        return [r[0] for r in rows]

    # ---- outbox ---------------------------------------------------------------

    async def _claim(
        self,
        tenant_id: int,
        kind: str,
        key: str,
        email: Email | None,
        now: datetime,
        *,
        item_count: int = 0,
        status: str = "sending",
        detail: str | None = None,
        scan_run_id: int | None = None,
        insight_id: int | None = None,
        channel: str = "email",
    ) -> Notification | None:
        """Chèn dòng outbox; None nếu khoá đã có (đã xử lý trước đó). Dòng "sending" tính là lần
        gửi thứ nhất."""
        sending = status == "sending"
        stmt = (
            insert(Notification)
            .values(
                tenant_id=tenant_id,
                kind=kind,
                dedupe_key=key,
                status=status,
                subject=(email.subject if email else "")[:SUBJECT_MAX],
                body_text=email.text if email else "",
                body_html=email.html if email else "",
                recipients=[],
                item_count=item_count,
                attempts=1 if sending else 0,
                last_attempt_at=now if sending else None,
                detail=detail,
                scan_run_id=scan_run_id,
                insight_id=insight_id,
                channel=channel,
            )
            .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
            .returning(Notification.id)
        )
        new_id = (await self._s.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            return None
        return await self._s.get(Notification, new_id)

    async def _skip(
        self, tenant_id: int, kind: str, key: str, detail: str, now: datetime, **extra: Any
    ) -> None:
        """Ghi dòng "skipped" để cron sau không tính lại (dashboard ẩn no_matches/disabled)."""
        await self._claim(tenant_id, kind, key, None, now, status="skipped", detail=detail, **extra)
        await self._s.commit()

    async def _subscriptions(
        self, tenant_id: int, channel: str, kind: str
    ) -> list[NotificationSubscription]:
        rows = (
            await self._s.execute(
                select(NotificationSubscription)
                .where(
                    NotificationSubscription.tenant_id == tenant_id,
                    NotificationSubscription.channel == channel,
                    NotificationSubscription.active.is_(True),
                )
                .order_by(NotificationSubscription.id)
            )
        ).scalars()
        return [r for r in rows if subscription_matches(r.kinds, kind)]

    async def _sent_today(self, channel: str, target: str, since: datetime) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count()).where(
                        NotificationDelivery.channel == channel,
                        func.lower(NotificationDelivery.target) == target.lower(),
                        NotificationDelivery.status == "sent",
                        NotificationDelivery.created_at >= since,
                    )
                )
            ).scalar_one()
        )

    async def _gate(
        self, row: Notification, sub: NotificationSubscription | None, now: datetime
    ) -> str | None:
        """Lý do không gửi tới người đăng ký này lúc này (giờ im lặng, quá trần tin/ngày)."""
        if sub is None or row.kind == ROW_TEST:
            return None
        tenant = await self._s.get(Tenant, row.tenant_id)
        local = tenant_now(tenant, now) if tenant else now
        if in_quiet_hours(local, sub.quiet_start, sub.quiet_end):
            return "skipped_quiet"
        if sub.max_per_day:
            midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
            if await self._sent_today(sub.channel, sub.target, midnight) >= sub.max_per_day:
                return "skipped_limit"
        return None

    def _tracked(self, token: str, url: str) -> str:
        path = url[len(self._base_url.rstrip("/")) :] if url.startswith(self._base_url) else url
        return f"{self._base_url.rstrip('/')}/api/notifications/t/{token}?to={quote(path or '/')}"

    def _resolve_url(self, token: str) -> str:
        return f"{self._base_url.rstrip('/')}/api/notifications/t/{token}/resolve"

    def _personalize(self, email: Email, token: str, locale: str) -> Email:
        """Gắn link theo dõi lượt nhấn và nút "Đã xử lý" cho từng người nhận (3.6)."""
        base = re.escape(self._base_url.rstrip("/"))
        html = re.sub(
            rf'href="({base}[^"]*)"',
            lambda m: f'href="{escape(self._tracked(token, unescape(m.group(1))))}"',
            email.html,
        )
        resolve = self._resolve_url(token)
        label = t(locale, "email.track.resolve")
        button = (
            '<tr><td style="padding:0 28px 20px"><a href="'
            + escape(resolve)
            + '" style="font:600 13px/1.8 Arial,sans-serif;color:#16a34a;text-decoration:none">'
            + f"✓ {escape(label)}</a></td></tr>"
        )
        tail = "</table></td></tr></table></body></html>"
        html = html[: -len(tail)] + button + tail if html.endswith(tail) else html + button
        return Email(email.subject, f"{email.text}\n\n{label}: {resolve}", html)

    def _main_url(self, row: Notification) -> str:
        if row.insight_id:
            return f"{self._base_url.rstrip('/')}/insights/{row.insight_id}"
        if row.kind == ROW_ALERTS:
            return f"{self._base_url.rstrip('/')}/today"
        return f"{self._base_url.rstrip('/')}/dashboard"

    async def _record(
        self,
        row: Notification,
        channel: str,
        target: str,
        status: str,
        token: str,
        *,
        external_id: str | None = None,
        cost: Decimal | None = None,
        error: str | None = None,
    ) -> None:
        self._s.add(
            NotificationDelivery(
                notification_id=row.id,
                tenant_id=row.tenant_id,
                channel=channel,
                target=target[:500],
                status=status,
                external_id=external_id,
                cost_vnd=cost,
                error=(error or None) and error[:500],
                token=token,
            )
        )

    async def _deliver(self, row: Notification, now: datetime) -> None:
        """Gửi tới mọi người nhận của kênh của dòng outbox và đặt trạng thái cuối."""
        if row.channel != "email":
            await self._deliver_channel(row, now)
            return
        legacy = await self.recipients(row.tenant_id)
        subs = await self._subscriptions(row.tenant_id, "email", row.kind)
        if not self._sender.configured:
            row.status, row.detail = "skipped", SKIP_NOT_CONFIGURED
            return
        targets: dict[str, tuple[str, NotificationSubscription | None]] = {}
        for addr in legacy:
            targets.setdefault(addr.lower(), (addr, None))
        for s_ in subs:
            targets.setdefault(s_.target.lower(), (s_.target, s_))
        if not targets:
            row.status, row.detail = "skipped", SKIP_NO_RECIPIENTS
            return
        tenant = await self._s.get(Tenant, row.tenant_id)
        locale = normalize_locale(tenant.insight_language) if tenant else DEFAULT_LOCALE
        base = Email(row.subject, row.body_text, row.body_html)
        plan: list[tuple[str, str]] = []  # (địa chỉ, token)
        for addr, sub in targets.values():
            token = _new_token()
            gate = await self._gate(row, sub, now)
            if gate:
                await self._record(row, "email", addr, gate, token)
                continue
            plan.append((addr, token))
        results = await asyncio.gather(
            *(self._sender.send(addr, self._personalize(base, tok, locale)) for addr, tok in plan),
            return_exceptions=True,
        )
        ok: list[str] = []
        errors: list[str] = []
        for (addr, token), r in zip(plan, results, strict=True):
            if isinstance(r, BaseException):
                err = f"{addr}: {type(r).__name__}: {r}"[:300]
                errors.append(err)
                log.warning("email_send_failed", notification_id=row.id, error=type(r).__name__)
                await self._record(row, "email", addr, "failed", token, error=err)
            else:
                ok.append(addr)
                await self._record(row, "email", addr, "sent", token)
        row.recipients = ok
        if ok:
            row.status, row.sent_at = "sent", now
            row.detail = "; ".join(errors) or None
        elif errors:
            row.status, row.detail = "failed", "; ".join(errors)
        else:
            row.status, row.detail = "skipped", "quiet_or_limit"

    async def _deliver_channel(self, row: Notification, now: datetime) -> None:
        notifier = self._notifiers.get(row.channel)
        if notifier is None or not notifier.configured:
            row.status, row.detail = "skipped", f"{row.channel}_not_configured"
            return
        subs = await self._subscriptions(row.tenant_id, row.channel, row.kind)
        if not subs:
            row.status, row.detail = "skipped", SKIP_NO_RECIPIENTS
            return
        tenant = await self._s.get(Tenant, row.tenant_id)
        local = tenant_now(tenant, now) if tenant else now
        lines = [ln.strip() for ln in (row.body_text or "").splitlines() if ln.strip()]
        summary = " · ".join(lines[1:3]) if len(lines) > 1 else row.subject
        ok, errors = [], []
        for sub in subs:
            token = _new_token()
            gate = await self._gate(row, sub, now)
            if gate:
                await self._record(row, row.channel, sub.target, gate, token)
                continue
            msg = Message(
                kind=row.kind,
                subject=row.subject,
                summary=summary,
                count=row.item_count,
                date_label=local.strftime("%d/%m/%Y"),
                url=self._tracked(token, self._main_url(row)),
                resolve_url=self._resolve_url(token),
            )
            try:
                res = await notifier.send(sub.target, msg, token)
            except Exception as exc:  # noqa: BLE001 — một người nhận lỗi không chặn người khác
                err = f"{sub.target}: {type(exc).__name__}: {exc}"[:300]
                errors.append(err)
                log.warning("channel_send_failed", channel=row.channel, error=type(exc).__name__)
                await self._record(row, row.channel, sub.target, "failed", token, error=err)
                continue
            ok.append(sub.target)
            await self._record(
                row,
                row.channel,
                sub.target,
                "sent",
                token,
                external_id=res.external_id,
                cost=res.cost_vnd,
            )
            if res.cost_vnd is not None:
                log.info("channel_sent", channel=row.channel, cost_vnd=str(res.cost_vnd))
        row.recipients = ok
        if ok:
            row.status, row.sent_at = "sent", now
            row.detail = "; ".join(errors) or None
        elif errors:
            row.status, row.detail = "failed", "; ".join(errors)
        else:
            row.status, row.detail = "skipped", "quiet_or_limit"

    async def _send(
        self, tenant_id: int, kind: str, key: str, email: Email, now: datetime, **extra: Any
    ) -> Notification | None:
        row = await self._claim(tenant_id, kind, key, email, now, **extra)
        if row is not None:
            # Chốt dòng "sending" trước khi gửi: worker chết giữa chừng thì retry() gửi tiếp,
            # và lần cron sau không chèn lại khoá này (không gửi trùng).
            await self._s.commit()
            await self._deliver(row, now)
            await self._s.commit()
            await self._fanout(tenant_id, kind, key, email, now, **extra)
        return row

    async def _fanout(
        self, tenant_id: int, kind: str, key: str, email: Email, now: datetime, **extra: Any
    ) -> None:
        """Cùng tin qua Zalo/webhook cho người đã đăng ký kênh đó (3.1): một dòng mỗi kênh."""
        for channel in FANOUT_CHANNELS:
            if not await self._subscriptions(tenant_id, channel, kind):
                continue
            row = await self._claim(
                tenant_id, kind, f"{key}:{channel}"[:128], email, now, channel=channel, **extra
            )
            if row is None:
                continue
            await self._s.commit()
            await self._deliver(row, now)
            await self._s.commit()

    async def _guarded(self, unit: str, work: Callable[[], Awaitable[int]]) -> int:
        """Một đơn vị việc lỗi (dữ liệu lạ, DB) chỉ bị bỏ qua lần này, không chặn đơn vị khác."""
        try:
            return await work()
        except Exception:  # noqa: BLE001
            log.exception("notification_dispatch_failed", unit=unit)
            await self._s.rollback()
            return 0

    # ---- các nguồn thông báo ----------------------------------------------------

    async def _candidate_runs(self, now: datetime) -> list[list[int]]:
        """Nhóm run cùng mốc quét (mỗi kênh một run, D9) đã chốt hết và đã chạy analytics. Một email
        mỗi mốc/tenant gộp mọi kênh (D11); nhóm còn run đang chạy thì đợi lần cron sau."""
        rows = await self._s.execute(
            select(ScanRun.id, ScanRun.trigger_key, ScanRun.channel, ScanRun.status)
            .where(
                ScanRun.scheduled_at >= now - LOOKBACK - timedelta(hours=2),
                # Run thị trường cả khu vực không phải mốc quét của tenant: không gửi email.
                ~ScanRun.trigger_key.startswith(MARKET_RUN_PREFIX),
            )
            .order_by(ScanRun.id)
        )
        slots: dict[str, list[tuple[int, str]]] = {}
        for run_id, key, channel, status_ in rows.all():
            slots.setdefault(slot_key(key, channel), []).append((run_id, status_))
        ready = [
            [r for r, _ in runs]
            for runs in slots.values()
            if all(st in ("completed", "partial") for _, st in runs)
        ]
        if not ready:
            return []
        ids = [r for g in ready for r in g]
        info = {
            r[0]: (r[1], r[2], r[3])
            for r in await self._s.execute(
                select(
                    ScanRun.id,
                    ScanRun.total_probes,
                    ScanRun.finished_at,
                    exists().where(HotelDateSnapshot.scan_run_id == ScanRun.id),
                ).where(ScanRun.id.in_(ids))
            )
        }
        out: list[list[int]] = []
        for group in ready:
            finished = [info[r][1] for r in group if info[r][1] is not None]
            if not finished or max(finished) < now - LOOKBACK:
                continue
            # Đợi mọi run có dữ liệu chạy xong analytics: gửi sớm thì sự kiện của kênh xong sau
            # (và sự kiện chéo kênh) mất hẳn vì khoá outbox đã có. Quá 2 giờ sau khi run cuối chốt
            # mà vẫn thiếu (analytics lỗi) thì gửi phần đã có.
            pending = [r for r in group if info[r][0] > 0 and not info[r][2]]
            analyzed = [r for r in group if info[r][2]]
            if not analyzed:
                continue
            if pending and max(finished) > now - ANALYTICS_GRACE:
                continue
            out.append(group)
        return out

    async def _run_tenants(self, run_ids: list[int]) -> list[TenantInfo]:
        probed = select(Probe.hotel_id).where(Probe.scan_run_id.in_(run_ids)).distinct()
        rows = await self._s.execute(
            select(Tenant)
            .where(
                Tenant.active.is_(True),
                exists().where(
                    TenantHotel.tenant_id == Tenant.id,
                    TenantHotel.active.is_(True),
                    TenantHotel.hotel_id.in_(probed),
                ),
            )
            .order_by(Tenant.id)
        )
        return [TenantInfo.of(t) for t in rows.scalars()]

    async def _run_events(self, tenant_id: int, run_ids: list[int]) -> list[EventFact]:
        rows = await self._s.execute(
            select(
                AvailabilityEvent,
                Hotel,
                TenantHotel.label,
                TenantHotel.role,
                RoomType.name,
                HotelDateSnapshot.currency,
            )
            .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
            .join(
                TenantHotel,
                and_(
                    TenantHotel.hotel_id == AvailabilityEvent.hotel_id,
                    TenantHotel.tenant_id == tenant_id,
                ),
            )
            .outerjoin(RoomType, RoomType.id == AvailabilityEvent.room_type_id)
            .outerjoin(
                HotelDateSnapshot,
                and_(
                    HotelDateSnapshot.hotel_id == AvailabilityEvent.hotel_id,
                    HotelDateSnapshot.stay_date == AvailabilityEvent.stay_date,
                    HotelDateSnapshot.scan_run_id == AvailabilityEvent.scan_run_id,
                ),
            )
            .where(
                AvailabilityEvent.scan_run_id.in_(run_ids),
                AvailabilityEvent.event_type.in_(
                    [
                        "sold_out",
                        "low_stock_enter",
                        "rooms_decrease",
                        "price_down",
                        "price_up",
                        "lowest_rate_shift",
                        "promo_start",
                        "restricted",
                    ]
                ),
                TenantHotel.active.is_(True),
            )
            .order_by(AvailabilityEvent.id)
        )
        return [
            EventFact(
                event_id=e.id,
                hotel_id=e.hotel_id,
                hotel_name=label or h.name or f"#{h.id}",
                room_type_name=rt_name if e.room_type_id is not None else None,
                stay_date=e.stay_date,
                event_type=e.event_type,
                from_value=e.from_value,
                to_value=e.to_value,
                delta=e.delta,
                currency=currency,
                role=role,
                reason=e.reason,
                detail=e.detail,
            )
            for e, h, label, role, rt_name, currency in rows.all()
        ]

    async def alerts_for_run(
        self, tenant: TenantInfo, run_ids: int | list[int], now: datetime
    ) -> list[AlertItem]:
        rules = await self.rules(tenant.id)
        if not any(rules[k].active for k in ALERT_KINDS):
            return []
        ids = [run_ids] if isinstance(run_ids, int) else run_ids
        events = await self._run_events(tenant.id, ids)
        if not events:
            return []
        dates = sorted({e.stay_date for e in events})
        market = {
            c.stay_date: NightMarket(
                c.competitors_sold_out,
                c.competitors_observed,
                c.competitors_low,
                c.price_index,
                c.sample,
                c.competitors_priced,
            )
            for c in await compset_by_day(
                self._s,
                tenant.id,
                dates[0],
                dates[-1],
                now=now,
            )
        }
        target = await self._target_index(tenant.id)
        return evaluate_alerts(
            rules, events, market, tenant_today(tenant, now), tenant.language, target
        )

    async def _target_index(self, tenant_id: int) -> Decimal:
        """Định vị mục tiêu của khách sạn của bạn (chiến lược giá, Phase 6); mặc định 100."""
        from app.market.models import PriceStrategy

        v = (
            await self._s.execute(
                select(PriceStrategy.target_index)
                .where(PriceStrategy.tenant_id == tenant_id)
                .order_by(PriceStrategy.hotel_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        return Decimal(v) if v is not None else Decimal(100)

    async def _alert_unit(self, tenant: TenantInfo, run_ids: list[int], now: datetime) -> int:
        # Khoá theo run nhỏ nhất của mốc (khoá cũ giữ nguyên để không gửi lại).
        run_id = min(run_ids)
        key = f"{ROW_ALERTS}:{tenant.id}:{run_id}"
        if await self._exists(key):
            return 0
        items = await self.alerts_for_run(tenant, run_ids, now)
        if not items:
            await self._skip(tenant.id, ROW_ALERTS, key, SKIP_NO_MATCHES, now, scan_run_id=run_id)
            return 0
        email = render_alerts(tenant.name, items, self._base_url, tenant.language)
        row = await self._send(
            tenant.id, ROW_ALERTS, key, email, now, item_count=len(items), scan_run_id=run_id
        )
        return int(row is not None and row.status == "sent")

    async def dispatch_alerts(self, now: datetime) -> int:
        sent = 0
        for run_ids in await self._candidate_runs(now):
            for tenant in await self._run_tenants(run_ids):
                sent += await self._guarded(
                    f"alerts:{tenant.id}:{min(run_ids)}",
                    partial(self._alert_unit, tenant, run_ids, now),
                )
        return sent

    async def _insight_unit(
        self,
        tenant: TenantInfo,
        insight_id: int,
        period_start: date,
        output: dict[str, Any] | None,
        now: datetime,
    ) -> int:
        key = f"insight:{insight_id}"
        kind = str(NotificationKind.DAILY_INSIGHT)
        if await self._exists(key):
            return 0
        rule = (await self.rules(tenant.id))[NotificationKind.DAILY_INSIGHT]
        if not rule.active or not output:
            await self._skip(tenant.id, kind, key, SKIP_DISABLED, now, insight_id=insight_id)
            return 0
        email = render_insight(
            tenant.name, insight_id, period_start, output, self._base_url, tenant.language
        )
        row = await self._send(tenant.id, kind, key, email, now, insight_id=insight_id)
        return int(row is not None and row.status == "sent")

    async def dispatch_insights(self, now: datetime) -> int:
        rows = await self._s.execute(
            select(Insight.id, Insight.period_start, Insight.output_json, Tenant)
            .join(Tenant, Tenant.id == Insight.tenant_id)
            .where(
                Insight.trigger == "daily",
                Insight.status == "completed",
                Insight.generated_at >= now - INSIGHT_LOOKBACK,
                Tenant.active.is_(True),
            )
            .order_by(Insight.id)
        )
        units = [(TenantInfo.of(t), iid, start, out) for iid, start, out, t in rows.all()]
        sent = 0
        for tenant, iid, start, out in units:
            sent += await self._guarded(
                f"insight:{iid}",
                partial(self._insight_unit, tenant, iid, start, out, now),
            )
        return sent

    async def _week_events(
        self, tenant_id: int, since: datetime, channel: str = "booking"
    ) -> list[WeekEvent]:
        """Sự kiện của kênh tham chiếu (cùng một lần hết phòng không bị đếm một lần mỗi kênh)."""
        rows = await self._s.execute(
            select(
                AvailabilityEvent.event_type,
                AvailabilityEvent.room_type_id,
                Hotel,
                TenantHotel.label,
            )
            .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
            .join(
                TenantHotel,
                and_(
                    TenantHotel.hotel_id == AvailabilityEvent.hotel_id,
                    TenantHotel.tenant_id == tenant_id,
                ),
            )
            .where(
                AvailabilityEvent.observed_at >= since,
                AvailabilityEvent.channel == channel,
                AvailabilityEvent.event_type.in_(COUNTED),
                TenantHotel.active.is_(True),
                TenantHotel.role == "competitor",
            )
        )
        return [
            WeekEvent(label or h.name or f"#{h.id}", et, rt is not None)
            for et, rt, h, label in rows.all()
        ]

    async def _weekly_unit(self, tenant: TenantInfo, now: datetime) -> int:
        key = weekly_due_key(tenant, now)
        if key is None or await self._exists(key):
            return 0
        kind = str(NotificationKind.WEEKLY_REPORT)
        if not (await self.rules(tenant.id))[NotificationKind.WEEKLY_REPORT].active:
            await self._skip(tenant.id, kind, key, SKIP_DISABLED, now)
            return 0
        today = tenant_today(tenant, now)
        end = today + timedelta(days=OUTLOOK_NIGHTS - 1)
        report = build_weekly_report(
            today,
            await self._week_events(tenant.id, now - timedelta(days=7)),
            await compset_by_day(self._s, tenant.id, today, end),
            holidays_between(tenant.country_code, today, end, tenant.language),
        )
        if report.empty:
            await self._skip(tenant.id, kind, key, SKIP_NO_MATCHES, now)
            return 0
        email = render_weekly(tenant.name, report, self._base_url, tenant.language)
        row = await self._send(tenant.id, kind, key, email, now)
        return int(row is not None and row.status == "sent")

    async def dispatch_weekly(self, now: datetime) -> int:
        rows = await self._s.execute(select(Tenant).where(Tenant.active.is_(True)))
        tenants = [TenantInfo.of(t) for t in rows.scalars()]
        sent = 0
        for tenant in tenants:
            sent += await self._guarded(
                f"weekly:{tenant.id}",
                partial(self._weekly_unit, tenant, now),
            )
        return sent

    async def _retry_one(self, nid: int, status: str, attempts: int, now: datetime) -> int:
        # Giành dòng nguyên tử: điều kiện trên trạng thái và số lần đã thấy, nên khi hai lần cron
        # chạy chồng nhau chỉ một bên cập nhật được và gửi.
        claimed = (
            await self._s.execute(
                update(Notification)
                .where(
                    Notification.id == nid,
                    Notification.status == status,
                    Notification.attempts == attempts,
                )
                .values(status="sending", attempts=attempts + 1, last_attempt_at=now)
                .returning(Notification.id)
            )
        ).scalar_one_or_none()
        if claimed is None:
            await self._s.rollback()
            return 0
        await self._s.commit()
        row = await self._s.get(Notification, nid, populate_existing=True)
        if row is None:
            return 0
        await self._deliver(row, now)
        await self._s.commit()
        return 1

    async def retry(self, now: datetime) -> int:
        """Thử lại email lỗi theo RETRY_BACKOFF và dòng "sending" bị bỏ dở (worker chết giữa
        chừng). Email thử không được thử lại: người dùng bấm lại nếu cần."""
        rows = await self._s.execute(
            select(
                Notification.id,
                Notification.status,
                Notification.attempts,
                Notification.last_attempt_at,
            ).where(
                Notification.created_at >= now - LOOKBACK,
                Notification.kind != ROW_TEST,
                Notification.attempts < MAX_ATTEMPTS,
                Notification.status.in_(["failed", "sending"]),
            )
        )
        n = 0
        for nid, status, attempts, last in rows.all():
            wait = SENDING_STALE if status == "sending" else RETRY_BACKOFF[max(attempts, 1) - 1]
            if last is not None and last > now - wait:
                continue
            n += await self._guarded(
                f"retry:{nid}",
                partial(self._retry_one, nid, status, attempts, now),
            )
        return n

    async def _stale_unit(self, tenant: TenantInfo, now: datetime) -> int:
        """Báo khách sạn khi dữ liệu một kênh đang quét cũ hơn một chu kỳ (0.7, 3.5): tối đa một
        tin mỗi ngày mỗi tenant."""
        key = f"stale:{tenant.id}:{tenant_today(tenant, now).isoformat()}"
        if await self._exists(key):
            return 0
        rule = (await self.rules(tenant.id))[NotificationKind.DATA_STALE]
        if not rule.active:
            return 0
        row = await self._s.get(Tenant, tenant.id)
        hours = stale_after_hours(list(row.scan_times) if row else [])
        ids = [
            h
            for (h,) in await self._s.execute(
                select(TenantHotel.hotel_id).where(
                    TenantHotel.tenant_id == tenant.id, TenantHotel.active.is_(True)
                )
            )
        ]
        if not ids:
            return 0
        channels = {
            c
            for (c,) in await self._s.execute(
                select(Listing.channel)
                .distinct()
                .where(Listing.hotel_id.in_(ids), Listing.status == "active")
            )
        }
        if not channels:
            return 0
        last = await channel_last_success(self._s, ids, since=now - timedelta(days=30))
        limit = now - timedelta(hours=hours)
        # Kênh chưa từng có dữ liệu (listing mới, đang chờ lượt quét đầu) không phải "dữ liệu cũ".
        stale = sorted(c for c in channels if c in last and last[c] < limit)
        if not stale:
            return 0
        since = min((last[c] for c in stale if c in last), default=None)
        email = render_stale(
            tenant.name,
            stale,
            tenant_now(tenant, since) if since else None,
            self._base_url,
            tenant.language,
        )
        sent = await self._send(tenant.id, ROW_STALE, key, email, now, item_count=len(stale))
        return int(sent is not None and sent.status == "sent")

    async def dispatch_stale(self, now: datetime) -> int:
        rows = await self._s.execute(select(Tenant).where(Tenant.active.is_(True)))
        tenants = [TenantInfo.of(t) for t in rows.scalars()]
        n = 0
        for tenant in tenants:
            n += await self._guarded(f"stale:{tenant.id}", partial(self._stale_unit, tenant, now))
        return n

    async def dispatch_due(self, now: datetime | None = None) -> DispatchReport:
        now = now or datetime.now(tz=UTC)
        report = DispatchReport()
        report.retried = await self.retry(now)
        report.alerts = await self.dispatch_alerts(now)
        report.insights = await self.dispatch_insights(now)
        report.weekly = await self.dispatch_weekly(now)
        report.stale = await self.dispatch_stale(now)
        return report

    async def send_test(self, tenant: Tenant, now: datetime | None = None) -> Notification:
        """Email thử tới mọi người nhận; tối đa một lần mỗi TEST_COOLDOWN cho mỗi tenant."""
        now = now or datetime.now(tz=UTC)
        recent = (
            await self._s.execute(
                select(
                    exists().where(
                        Notification.tenant_id == tenant.id,
                        Notification.kind == ROW_TEST,
                        Notification.created_at > func.now() - TEST_COOLDOWN,
                    )
                )
            )
        ).scalar()
        if recent:
            raise TestTooSoon
        key = f"{ROW_TEST}:{tenant.id}:{now.strftime('%Y%m%d%H%M%S%f')}"
        email = render_test(tenant.name, self._base_url, normalize_locale(tenant.insight_language))
        row = await self._send(tenant.id, ROW_TEST, key, email, now)
        if row is None:
            raise TestTooSoon
        return row

    async def _exists(self, key: str) -> bool:
        return bool(
            (await self._s.execute(select(exists().where(Notification.dedupe_key == key)))).scalar()
        )

    async def mark_rule(
        self, tenant_id: int, kind: NotificationKind, active: bool, params: dict[str, int]
    ) -> None:
        stmt = (
            insert(NotificationRule)
            .values(tenant_id=tenant_id, kind=str(kind), active=active, params=params)
            .on_conflict_do_update(
                index_elements=[NotificationRule.tenant_id, NotificationRule.kind],
                set_={"active": active, "params": params, "updated_at": datetime.now(tz=UTC)},
            )
        )
        await self._s.execute(stmt)
