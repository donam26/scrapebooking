import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.db.models import Listing, Tenant, TenantHotel
from app.db.partitions import ensure_room_snapshot_partitions
from app.logging import get_logger
from app.marketscan.scheduling import MarketScheduler, MarketTickReport
from app.ops.alerts import Alerter, AlertThrottle, block_rate_alert
from app.ops.metrics import QUEUE_DEPTH, RUNS_CREATED
from app.ops.proxy_check import ProxyHealth, proxy_alert
from app.repo.runs import ScanRunRepository
from app.scheduler.channel_pause import ChannelPauses, should_pause
from app.scheduler.planning import (
    TenantSchedule,
    WatchRow,
    build_hotel_plans,
    channel_trigger_key,
    compute_triggers,
    missed_slots,
    rows_by_channel,
    trigger_key,
)
from app.scheduler.queue import JobQueue

# Listing được quét: đã xác minh. `unverified` chờ verify, `broken`/`paused`/`suggested` không quét.
SCANNABLE_LISTING = "active"

ProxyChecker = Callable[[], Awaitable[list[ProxyHealth]]]


async def load_watch_rows(
    s: AsyncSession, tenant_ids: tuple[int, ...] | None = None
) -> list[WatchRow]:
    """Một dòng mỗi (tenant, listing đang quét). tenant_ids None: mọi tenant đang hoạt động."""
    stmt = (
        select(
            TenantHotel.tenant_id,
            TenantHotel.hotel_id,
            Tenant.horizon_days,
            Tenant.timezone,
            Listing.channel,
        )
        .join(Tenant, Tenant.id == TenantHotel.tenant_id)
        .join(Listing, Listing.hotel_id == TenantHotel.hotel_id)
        .where(
            TenantHotel.active.is_(True),
            Tenant.active.is_(True),
            Listing.status == SCANNABLE_LISTING,
        )
    )
    if tenant_ids is not None:
        stmt = stmt.where(TenantHotel.tenant_id.in_(tenant_ids))
    return [WatchRow(r[0], r[1], r[2], r[3], r[4]) for r in await s.execute(stmt)]


log = get_logger(__name__)


@dataclass
class TickReport:
    created_runs: list[int] = field(default_factory=list)
    catch_up_run: int | None = None
    expired_runs: list[int] = field(default_factory=list)
    reenqueued: int = 0
    alerts: list[str] = field(default_factory=list)
    paused_channels: list[str] = field(default_factory=list)
    market: MarketTickReport | None = None


class SchedulerService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: JobQueue,
        clock: Clock,
        deadline: timedelta,
        alerter: Alerter,
        lookback: timedelta = timedelta(minutes=10),
        stale_after: timedelta = timedelta(minutes=5),
        pauses: ChannelPauses | None = None,
        proxy_checker: ProxyChecker | None = None,
        block_threshold: float = 0.2,
        block_min_probes: int = 20,
        pause_minutes: int = 30,
        proxy_check_every: timedelta = timedelta(minutes=15),
        market: MarketScheduler | None = None,
        market_deadline: timedelta | None = None,
    ) -> None:
        self._sf = session_factory
        self._queue = queue
        self._clock = clock
        self._deadline = deadline
        self._alerter = alerter
        self._lookback = lookback
        self._stale_after = stale_after
        self._throttle = AlertThrottle(clock, min_gap=timedelta(minutes=30))
        self._pauses = pauses
        self._proxy_checker = proxy_checker
        self._block_threshold = block_threshold
        self._block_min_probes = block_min_probes
        self._pause_minutes = pause_minutes
        self._proxy_check_every = proxy_check_every
        self._proxy_checked_at: datetime | None = None
        # Thị trường toàn thành phố (app/marketscan): lịch quét danh sách/chi tiết theo khu vực.
        self._market = market
        self._market_deadline = market_deadline
        self._partitions_checked_on: date | None = None
        # Tick thành công gần nhất. None (vừa khởi động) hoặc cách quá `lookback` nghĩa là
        # scheduler đã không chạy một quãng: mốc quét rơi vào quãng đó có thể đã bị lỡ.
        self._last_tick_at: datetime | None = None

    async def _load_tenants(self, s: AsyncSession) -> list[TenantSchedule]:
        rows = (await s.execute(select(Tenant).where(Tenant.active.is_(True)))).scalars().all()
        return [TenantSchedule(t.id, t.timezone, tuple(t.scan_times), t.horizon_days) for t in rows]

    async def _load_watch_rows(
        self, s: AsyncSession, tenant_ids: tuple[int, ...]
    ) -> list[WatchRow]:
        return await load_watch_rows(s, tenant_ids)

    async def _paused(self, channel: str) -> bool:
        return self._pauses is not None and await self._pauses.is_paused(channel)

    async def tick(self) -> TickReport:
        report = TickReport()
        now = self._clock.now()
        async with self._sf() as s:
            repo = ScanRunRepository(s)
            tenants = await self._load_tenants(s)
            for trigger in compute_triggers(tenants, now, self._lookback):
                rows = await self._load_watch_rows(s, trigger.tenant_ids)
                for channel, channel_rows in rows_by_channel(rows).items():
                    if await self._paused(channel):
                        log.warning("channel_paused_skip_run", channel=channel, trigger=trigger.key)
                        continue
                    run_id = await self._start_run(
                        s,
                        repo,
                        channel_trigger_key(trigger.key, channel),
                        trigger.at,
                        channel_rows,
                        channel,
                    )
                    if run_id is not None:
                        report.created_runs.append(run_id)

            # Chốt run quá hạn trước: job dở của run đã chết không bị đẩy lại hàng đợi và không được
            # tính là "đã quét" khi quét bù.
            report.expired_runs = await repo.expire_runs(self._deadline, now, self._market_deadline)
            await s.commit()
            if report.expired_runs:
                log.warning("scan_runs_expired", run_ids=report.expired_runs)
                enqueue_analytics = getattr(self._queue, "enqueue_analytics", None)
                if enqueue_analytics is not None:
                    for run_id in report.expired_runs:
                        await enqueue_analytics(run_id)

            for run_id, hotel_id, channel in await repo.stale_queued_jobs(now - self._stale_after):
                await self._queue.enqueue_probe(run_id, hotel_id, channel)
                report.reenqueued += 1

            if self._market is not None:
                try:
                    report.market = await self._market.tick(now)
                except Exception:  # noqa: BLE001 — lỗi thị trường không được chặn lịch quét thường
                    log.exception("market_tick_failed")

            if self._last_tick_at is None or now - self._last_tick_at > self._lookback:
                for run_id in await self._catch_up(s, repo, tenants, now):
                    report.catch_up_run = report.catch_up_run or run_id
                    report.created_runs.append(run_id)

            stats = await repo.probe_stats_since(now - timedelta(minutes=15))
            for channel, (total, blocked) in sorted(stats.items()):
                msg = block_rate_alert(
                    total, blocked, self._block_min_probes, self._block_threshold
                )
                if msg and self._throttle.should_send(f"block_rate:{channel}"):
                    msg = f"[{channel}] {msg}"
                    await self._alerter.send(msg)
                    report.alerts.append(msg)
                if (
                    self._pauses is not None
                    and should_pause(total, blocked, self._block_min_probes, self._block_threshold)
                    and not await self._pauses.is_paused(channel)
                ):
                    await self._pauses.pause(
                        channel, self._pause_minutes, f"block rate {blocked}/{total}"
                    )
                    report.paused_channels.append(channel)
                    text = (
                        f"⏸ Channel {channel} paused {self._pause_minutes} min: "
                        f"{blocked}/{total} probes blocked in 15 min; other channels continue"
                    )
                    await self._alerter.send(text)
                    report.alerts.append(text)

            await self._check_proxies(now, report)

            today = now.date()
            if self._partitions_checked_on != today:
                conn = await s.connection()
                created = await ensure_room_snapshot_partitions(conn, today, months=3)
                await s.commit()
                self._partitions_checked_on = today
                if created:
                    log.info("partitions_created", names=created)
        self._last_tick_at = now
        return report

    async def _check_proxies(self, now: datetime, report: TickReport) -> None:
        if self._proxy_checker is None:
            return
        if (
            self._proxy_checked_at is not None
            and now - self._proxy_checked_at < self._proxy_check_every
        ):
            return
        self._proxy_checked_at = now
        try:
            results = await self._proxy_checker()
        except Exception:  # noqa: BLE001
            log.exception("proxy_check_failed")
            return
        msg = proxy_alert(results)
        if msg and self._throttle.should_send("proxy"):
            await self._alerter.send(msg)
            report.alerts.append(msg)

    async def _start_run(
        self,
        s: AsyncSession,
        repo: ScanRunRepository,
        key: str,
        at: datetime,
        rows: list[WatchRow],
        channel: str,
    ) -> int | None:
        """Tạo run `key` của một kênh (một job mỗi khách sạn trong `rows`) và đẩy job vào hàng đợi
        của kênh. Trả None khi không có khách sạn nào hoặc `key` đã có run."""
        plans = build_hotel_plans(rows, at)
        if not plans:
            return None
        run = await repo.create_run(key, at, plans, channel)
        if run is None:
            return None
        await s.commit()
        for plan in plans:
            await self._queue.enqueue_probe(run.id, plan.hotel_id, channel)
        RUNS_CREATED.inc()
        QUEUE_DEPTH.set(len(plans))
        log.info("scan_run_created", run_id=run.id, trigger=key, jobs=len(plans), channel=channel)
        return run.id

    async def _catch_up(
        self,
        s: AsyncSession,
        repo: ScanRunRepository,
        tenants: list[TenantSchedule],
        now: datetime,
    ) -> list[int]:
        """Quét bù sau một quãng scheduler không chạy (máy tắt, mất DB…): listing nào chưa được
        quét kể từ mốc gần nhất của tenant được gom vào một run mỗi kênh, bắt đầu ngay. Phạm vi quét
        tính từ hôm nay. Mốc đã có run (kể cả "Quét ngay") thì không quét lại."""
        rows: list[WatchRow] = []
        missed = missed_slots(tenants, now, self._lookback)
        for tenant_id, slot in missed.items():
            tenant_rows = await self._load_watch_rows(s, (tenant_id,))
            for channel, channel_rows in rows_by_channel(tenant_rows).items():
                scanned = await repo.hotels_scanned_since(
                    [r.hotel_id for r in channel_rows], slot, channel
                )
                rows += [r for r in channel_rows if r.hotel_id not in scanned]
        created: list[int] = []
        for channel, channel_rows in rows_by_channel(rows).items():
            if await self._paused(channel):
                continue
            key = channel_trigger_key(f"catchup:{trigger_key(now)}", channel)
            run_id = await self._start_run(s, repo, key, now, channel_rows, channel)
            if run_id is None:
                continue
            created.append(run_id)
            since = min(missed.values()).strftime("%Y-%m-%d %H:%M UTC")
            await self._alerter.send(
                f"Scheduler missed scan slots since {since} (stopped or failing); "
                f"catch-up run #{run_id} [{channel}] for "
                f"{len({r.hotel_id for r in channel_rows})} hotels"
            )
        return created

    async def run_forever(self, interval_seconds: float = 60.0) -> None:
        log.info("scheduler_started", interval=interval_seconds)
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler_tick_failed")
            await asyncio.sleep(interval_seconds)
