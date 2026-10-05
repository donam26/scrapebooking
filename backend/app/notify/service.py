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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.channels.registry import sort_channels
from app.config import Settings
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateSnapshot,
    Insight,
    Notification,
    NotificationRecipient,
    NotificationRule,
    Probe,
    RoomType,
    ScanRun,
    Tenant,
    TenantHotel,
)
from app.holidays.data import holidays_between
from app.i18n import DEFAULT_LOCALE, normalize_locale
from app.logging import get_logger
from app.notify.alert_rules import AlertItem, EventFact, NightMarket, evaluate_alerts
from app.notify.email_sender import EmailSender
from app.notify.kinds import ALERT_KINDS, NotificationKind, RuleConfig, effective_rules
from app.notify.render import Email, render_alerts, render_insight, render_test, render_weekly
from app.notify.weekly import COUNTED, OUTLOOK_NIGHTS, WeekEvent, build_weekly_report
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


class TestTooSoon(Exception):
    pass


@dataclass
class DispatchReport:
    alerts: int = 0
    insights: int = 0
    weekly: int = 0
    retried: int = 0


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
    reference_channel: str = "booking"
    language: str = DEFAULT_LOCALE  # ngôn ngữ báo cáo (`insight_language`): chữ của mọi email

    @classmethod
    def of(cls, t: Tenant) -> "TenantInfo":
        return cls(
            t.id,
            t.name,
            t.timezone,
            t.country_code,
            t.reference_channel,
            normalize_locale(t.insight_language),
        )


WEEKLY_HOUR = 8  # thứ Hai, giờ địa phương của tenant


def slot_key(trigger_key: str, channel: str) -> str:
    """Mốc quét của run: bỏ hậu tố ":<kênh>" (run đa kênh cùng mốc gộp một email)."""
    suffix = f":{channel}"
    return trigger_key[: -len(suffix)] if trigger_key.endswith(suffix) else trigger_key


def _price_or_max(value: str | None) -> Decimal:
    try:
        return Decimal(value) if value else Decimal("Infinity")
    except ArithmeticError:
        return Decimal("Infinity")


def merge_channel_events(
    rows: list[tuple[str, EventFact]], reference_channel: str = "booking"
) -> list[EventFact]:
    """Gộp cùng một sự kiện (khách sạn, loại phòng, đêm, loại) xảy ra trên nhiều kênh của một mốc
    thành một dòng mang danh sách kênh. Giá trị lấy từ kênh tham chiếu nếu có. Hết phòng kèm
    channel_closed (kênh khác vẫn bán) được đánh dấu `open_elsewhere`."""
    groups: dict[tuple[int, str | None, date, str], list[tuple[str, EventFact]]] = {}
    for channel, fact in rows:
        groups.setdefault(
            (fact.hotel_id, fact.room_type_name, fact.stay_date, fact.event_type), []
        ).append((channel, fact))
    closed: dict[tuple[int, date, str], set[str]] = {}
    for (hotel_id, _rt, stay, et), members in groups.items():
        if et == "channel_closed":
            for channel, fact in members:
                closed.setdefault((hotel_id, stay, channel), set()).update(
                    c for c in (fact.from_value or "").split(",") if c
                )
    out: list[EventFact] = []
    for (hotel_id, _rt, stay, et), members in groups.items():
        if et == "channel_closed":
            continue
        members.sort(key=lambda m: (m[0] != reference_channel, m[0]))
        channels = tuple(sort_channels(m[0] for m in members))
        if et == "parity_gap":
            # Các run cùng mốc chốt lệch giờ: kênh phân tích trước so với dữ liệu kênh khác chưa có.
            # Chỉ giữ kênh thật sự rẻ nhất (giá thấp nhất) của đêm đó.
            members.sort(key=lambda m: _price_or_max(m[1].to_value))
            channels = (members[0][0],)
        open_elsewhere: set[str] = set()
        if et == "sold_out":
            for channel in channels:
                open_elsewhere |= closed.get((hotel_id, stay, channel), set())
            open_elsewhere -= set(channels)
        base = members[0][1]
        out.append(
            EventFact(
                **{
                    **base.__dict__,
                    "channels": channels,
                    "open_elsewhere": tuple(sort_channels(open_elsewhere)),
                }
            )
        )
    return sorted(out, key=lambda f: f.event_id)


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


class NotificationService:
    def __init__(self, session: AsyncSession, sender: EmailSender, settings: Settings) -> None:
        self._s = session
        self._sender = sender
        self._base_url = settings.app_base_url

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

    async def _deliver(self, row: Notification, now: datetime) -> None:
        """Gửi tới mọi người nhận (song song, mỗi người một email) và đặt trạng thái cuối."""
        to = await self.recipients(row.tenant_id)
        if not self._sender.configured:
            row.status, row.detail = "skipped", SKIP_NOT_CONFIGURED
            return
        if not to:
            row.status, row.detail = "skipped", SKIP_NO_RECIPIENTS
            return
        email = Email(row.subject, row.body_text, row.body_html)
        results = await asyncio.gather(
            *(self._sender.send(addr, email) for addr in to), return_exceptions=True
        )
        ok = [addr for addr, r in zip(to, results, strict=True) if not isinstance(r, BaseException)]
        errors = [
            f"{addr}: {type(r).__name__}: {r}"[:300]
            for addr, r in zip(to, results, strict=True)
            if isinstance(r, BaseException)
        ]
        for err in errors:
            log.warning(
                "email_send_failed", notification_id=row.id, error=err.split(":", 2)[1].strip()
            )
        row.recipients = ok
        if ok:
            row.status, row.sent_at = "sent", now
            row.detail = "; ".join(errors) or None
        else:
            row.status, row.detail = "failed", "; ".join(errors)

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
        return row

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

    async def _run_events(
        self, tenant_id: int, run_ids: list[int], reference_channel: str = "booking"
    ) -> list[EventFact]:
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
                    ["sold_out", "low_stock_enter", "price_down", "channel_closed", "parity_gap"]
                ),
                TenantHotel.active.is_(True),
            )
            .order_by(AvailabilityEvent.id)
        )
        return merge_channel_events(
            [
                (
                    e.channel,
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
                    ),
                )
                for e, h, label, role, rt_name, currency in rows.all()
            ],
            reference_channel,
        )

    async def alerts_for_run(
        self, tenant: TenantInfo, run_ids: int | list[int], now: datetime
    ) -> list[AlertItem]:
        rules = await self.rules(tenant.id)
        if not any(rules[k].active for k in ALERT_KINDS):
            return []
        ids = [run_ids] if isinstance(run_ids, int) else run_ids
        events = await self._run_events(tenant.id, ids, tenant.reference_channel)
        if not events:
            return []
        dates = sorted({e.stay_date for e in events})
        market = {
            c.stay_date: NightMarket(c.competitors_sold_out, c.competitors_observed)
            for c in await compset_by_day(
                self._s,
                tenant.id,
                dates[0],
                dates[-1],
                channel=tenant.reference_channel,
            )
        }
        return evaluate_alerts(rules, events, market, tenant_today(tenant, now), tenant.language)

    async def _alert_unit(self, tenant: TenantInfo, run_ids: list[int], now: datetime) -> int:
        # Khoá theo run nhỏ nhất của mốc: mốc chỉ có một run (dữ liệu trước đa kênh) giữ khoá cũ.
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
            await self._week_events(tenant.id, now - timedelta(days=7), tenant.reference_channel),
            await compset_by_day(self._s, tenant.id, today, end, channel=tenant.reference_channel),
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

    async def dispatch_due(self, now: datetime | None = None) -> DispatchReport:
        now = now or datetime.now(tz=UTC)
        report = DispatchReport()
        report.retried = await self.retry(now)
        report.alerts = await self.dispatch_alerts(now)
        report.insights = await self.dispatch_insights(now)
        report.weekly = await self.dispatch_weekly(now)
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
