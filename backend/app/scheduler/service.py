import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.channels.registry import ChannelCode
from app.clock import Clock
from app.db.models import HotelDateSnapshot, Listing, ScanRun, Tenant, TenantHotel
from app.db.partitions import ensure_room_snapshot_partitions
from app.logging import get_logger
from app.marketscan.scheduling import MarketScheduler, MarketTickReport
from app.ops.alerts import Alerter, AlertThrottle, block_rate_alert
from app.ops.metrics import (
    ANALYTICS_LAG,
    ARQ_QUEUE_DEPTH,
    LAST_RUN_JOBS,
    RUNS_CREATED,
    RUNS_EXPIRED,
    SCHEDULER_TICK_SECONDS,
    SCHEDULER_TICKS,
)
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
from app.scheduler.queue import JOBS_QUEUE, JobQueue, collector_queue

# Listing được quét: đã xác minh. `unverified` chờ verify, `broken`/`paused`/`suggested` không quét.
SCANNABLE_LISTING = "active"

# Khoá leader giữa các bản sao scheduler: `pg_try_advisory_lock` (mức session) trên một kết nối
# riêng, lấy đầu tick và trả cuối tick. Bản sao không lấy được thì bỏ tick ("scheduler_standby").
# Tiến trình giữ khoá chết thì Postgres giải phóng khi kết nối đứt → bản sao kia tiếp quản ở tick
# sau. Hai bản sao lệch pha có thể luân phiên tick: vô hại vì mọi bước idempotent và throttle cảnh
# báo nằm trong Redis.
SCHEDULER_LOCK_NAME = "scrapebooking.scheduler"
STANDBY_LOG_EVERY = timedelta(minutes=1)
# Hàng đợi arq đo độ sâu mỗi tick (nhãn = phần sau `arq:queue:`).
MONITORED_QUEUES = sorted({JOBS_QUEUE, *(collector_queue(str(c)) for c in ChannelCode)})
ANALYTICS_LAG_WINDOW = timedelta(days=7)

ProxyChecker = Callable[[], Awaitable[list[ProxyHealth]]]
ProbeStats = dict[str, tuple[int, int]]  # kênh -> (tổng probe, số bị chặn) 15 phút qua


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
    skipped: bool = False  # bản sao standby: không lấy được khoá leader, không làm gì


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
        # Queue thật (ArqJobQueue) có client Redis: throttle cảnh báo và độ sâu hàng đợi dùng nó;
        # queue giả trong test không có → throttle trong bộ nhớ, không đo hàng đợi.
        self._redis = getattr(queue, "redis", None)
        self._throttle = AlertThrottle(clock, min_gap=timedelta(minutes=30), redis=self._redis)
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
        self._standby_logged_at: datetime | None = None

    async def _load_tenants(self, s: AsyncSession) -> list[TenantSchedule]:
        rows = (await s.execute(select(Tenant).where(Tenant.active.is_(True)))).scalars().all()
        return [TenantSchedule(t.id, t.timezone, tuple(t.scan_times), t.horizon_days) for t in rows]

    async def _load_watch_rows(
        self, s: AsyncSession, tenant_ids: tuple[int, ...]
    ) -> list[WatchRow]:
        return await load_watch_rows(s, tenant_ids)

    async def _paused(self, channel: str) -> bool:
        return self._pauses is not None and await self._pauses.is_paused(channel)

    @asynccontextmanager
    async def _leader_lock(self) -> AsyncIterator[bool]:
        """Giữ khoá leader trong thân `with`; yield False khi bản sao khác đang giữ."""
        engine = self._sf.kw.get("bind")
        if not isinstance(engine, AsyncEngine):
            yield True  # session factory không gắn engine (test với session giả): không khoá
            return
        params = {"name": SCHEDULER_LOCK_NAME}
        async with engine.connect() as conn:
            acquired = bool(
                (
                    await conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:name))"), params)
                ).scalar_one()
            )
            # Khoá theo session, không theo transaction: kết thúc transaction ngay để kết nối không
            # "idle in transaction" suốt tick (idle_in_transaction_session_timeout sẽ cắt nó).
            await conn.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        await conn.execute(
                            text("SELECT pg_advisory_unlock(hashtext(:name))"), params
                        )
                        await conn.commit()
                    except Exception:  # noqa: BLE001
                        # Không trả được khoá trên kết nối này: huỷ kết nối để Postgres giải phóng
                        # khoá; nếu để pool giữ lại, chính tiến trình này cũng không lấy lại được.
                        log.exception("scheduler_lock_release_failed")
                        await conn.invalidate()

    def _log_standby(self, now: datetime) -> None:
        if self._standby_logged_at is None or now - self._standby_logged_at >= STANDBY_LOG_EVERY:
            self._standby_logged_at = now
            log.info("scheduler_standby", lock=SCHEDULER_LOCK_NAME)

    async def tick(self) -> TickReport:
        t0 = time.perf_counter()
        now = self._clock.now()
        async with self._leader_lock() as leader:
            if not leader:
                self._log_standby(now)
                SCHEDULER_TICKS.labels("standby").inc()
                return TickReport(skipped=True)
            try:
                report, stats, pending_alerts = await self._tick_db(now)
            except Exception:
                SCHEDULER_TICKS.labels("error").inc()
                raise
        # Ngoài khoá và ngoài transaction: gửi cảnh báo (SMTP tới 20 s/người nhận), tạm dừng kênh
        # (Redis), kiểm tra proxy (20 s/proxy) — không giữ kết nối DB trong lúc chờ mạng.
        await self._after_commit(now, report, stats, pending_alerts)
        await self._measure_queues()
        self._last_tick_at = now
        SCHEDULER_TICKS.labels("ok").inc()
        SCHEDULER_TICK_SECONDS.observe(time.perf_counter() - t0)
        return report

    async def _tick_db(self, now: datetime) -> tuple[TickReport, ProbeStats, list[str]]:
        """Phần tick cần DB: tạo run, chốt run quá hạn, đẩy lại job kẹt, thị trường, quét bù, đọc
        thống kê. Mọi transaction đều commit trước khi trả về; cảnh báo cần gửi trả trong
        `pending_alerts` để gửi sau."""
        report = TickReport()
        pending_alerts: list[str] = []
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
                RUNS_EXPIRED.inc(len(report.expired_runs))
                log.warning("scan_runs_expired", run_ids=report.expired_runs)
                enqueue_analytics = getattr(self._queue, "enqueue_analytics", None)
                if enqueue_analytics is not None:
                    for run_id in report.expired_runs:
                        await enqueue_analytics(run_id)

            stale = await repo.stale_queued_jobs(now - self._stale_after)
            await s.commit()  # kết thúc transaction đọc trước khi gọi Redis từng job
            for run_id, hotel_id, channel in stale:
                await self._queue.enqueue_probe(run_id, hotel_id, channel)
                report.reenqueued += 1

            if self._market is not None:
                try:
                    report.market = await self._market.tick(now)
                except Exception:  # noqa: BLE001 — lỗi thị trường không được chặn lịch quét thường
                    log.exception("market_tick_failed")

            if self._last_tick_at is None or now - self._last_tick_at > self._lookback:
                for run_id, alert in await self._catch_up(s, repo, tenants, now):
                    report.catch_up_run = report.catch_up_run or run_id
                    report.created_runs.append(run_id)
                    pending_alerts.append(alert)

            stats = await repo.probe_stats_since(now - timedelta(minutes=15))
            ANALYTICS_LAG.set(await self._analytics_lag_seconds(s, now))
            await s.commit()

            today = now.date()
            if self._partitions_checked_on != today:
                conn = await s.connection()
                created = await ensure_room_snapshot_partitions(conn, today, months=3)
                await s.commit()
                self._partitions_checked_on = today
                if created:
                    log.info("partitions_created", names=created)
        return report, stats, pending_alerts

    async def _after_commit(
        self, now: datetime, report: TickReport, stats: ProbeStats, pending_alerts: list[str]
    ) -> None:
        for msg in pending_alerts:
            await self._alerter.send(msg)
            report.alerts.append(msg)
        for channel, (total, blocked) in sorted(stats.items()):
            msg = block_rate_alert(total, blocked, self._block_min_probes, self._block_threshold)
            if msg and await self._throttle.should_send(f"block_rate:{channel}"):
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
                text_ = (
                    f"⏸ Channel {channel} paused {self._pause_minutes} min: "
                    f"{blocked}/{total} probes blocked in 15 min; other channels continue"
                )
                await self._alerter.send(text_)
                report.alerts.append(text_)
        await self._check_proxies(now, report)

    async def _analytics_lag_seconds(self, s: AsyncSession, now: datetime) -> float:
        """Tuổi của run đã chốt lâu nhất (7 ngày gần đây) chưa có hotel_date_snapshots — cùng điều
        kiện với AnalyticsService.pending_run_ids; 0 khi không có."""
        analyzed = exists().where(HotelDateSnapshot.scan_run_id == ScanRun.id)
        oldest = (
            await s.execute(
                select(func.min(ScanRun.finished_at)).where(
                    ScanRun.status.in_(["completed", "partial"]),
                    ScanRun.total_probes > 0,
                    ScanRun.finished_at >= now - ANALYTICS_LAG_WINDOW,
                    ~analyzed,
                )
            )
        ).scalar_one()
        if oldest is None:
            return 0.0
        return max(0.0, (now - oldest).total_seconds())

    async def _measure_queues(self) -> None:
        if self._redis is None:
            return
        try:
            for name in MONITORED_QUEUES:
                depth = await self._redis.zcard(name)
                ARQ_QUEUE_DEPTH.labels(name.removeprefix("arq:queue:")).set(depth)
        except Exception:  # noqa: BLE001 — đo lường không được làm hỏng tick
            log.warning("queue_depth_failed", exc_info=True)

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
        if msg and await self._throttle.should_send("proxy"):
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
        LAST_RUN_JOBS.set(len(plans))
        log.info("scan_run_created", run_id=run.id, trigger=key, jobs=len(plans), channel=channel)
        return run.id

    async def _catch_up(
        self,
        s: AsyncSession,
        repo: ScanRunRepository,
        tenants: list[TenantSchedule],
        now: datetime,
    ) -> list[tuple[int, str]]:
        """Quét bù sau một quãng scheduler không chạy (máy tắt, mất DB…): listing nào chưa được
        quét kể từ mốc gần nhất của tenant được gom vào một run mỗi kênh, bắt đầu ngay. Phạm vi quét
        tính từ hôm nay. Mốc đã có run (kể cả "Quét ngay") thì không quét lại. Trả (run, cảnh báo)
        — cảnh báo gửi sau khi tick đã commit."""
        rows: list[WatchRow] = []
        missed = missed_slots(tenants, now, self._lookback)
        for tenant_id, slot in missed.items():
            tenant_rows = await self._load_watch_rows(s, (tenant_id,))
            for channel, channel_rows in rows_by_channel(tenant_rows).items():
                scanned = await repo.hotels_scanned_since(
                    [r.hotel_id for r in channel_rows], slot, channel
                )
                rows += [r for r in channel_rows if r.hotel_id not in scanned]
        created: list[tuple[int, str]] = []
        for channel, channel_rows in rows_by_channel(rows).items():
            if await self._paused(channel):
                continue
            key = channel_trigger_key(f"catchup:{trigger_key(now)}", channel)
            run_id = await self._start_run(s, repo, key, now, channel_rows, channel)
            if run_id is None:
                continue
            since = min(missed.values()).strftime("%Y-%m-%d %H:%M UTC")
            created.append(
                (
                    run_id,
                    f"Scheduler missed scan slots since {since} (stopped or failing); "
                    f"catch-up run #{run_id} [{channel}] for "
                    f"{len({r.hotel_id for r in channel_rows})} hotels",
                )
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
