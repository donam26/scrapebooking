import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.db.models import Tenant, TenantHotel
from app.db.partitions import ensure_room_snapshot_partitions
from app.logging import get_logger
from app.ops.alerts import Alerter, AlertThrottle, block_rate_alert
from app.ops.metrics import QUEUE_DEPTH, RUNS_CREATED
from app.repo.runs import ScanRunRepository
from app.scheduler.planning import TenantSchedule, WatchRow, build_hotel_plans, compute_triggers
from app.scheduler.queue import JobQueue

log = get_logger(__name__)


@dataclass
class TickReport:
    created_runs: list[int] = field(default_factory=list)
    expired_runs: list[int] = field(default_factory=list)
    reenqueued: int = 0
    alerts: list[str] = field(default_factory=list)


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
    ) -> None:
        self._sf = session_factory
        self._queue = queue
        self._clock = clock
        self._deadline = deadline
        self._alerter = alerter
        self._lookback = lookback
        self._stale_after = stale_after
        self._throttle = AlertThrottle(clock, min_gap=timedelta(minutes=30))
        self._partitions_checked_on: date | None = None

    async def _load_tenants(self, s: AsyncSession) -> list[TenantSchedule]:
        rows = (await s.execute(select(Tenant).where(Tenant.active.is_(True)))).scalars().all()
        return [TenantSchedule(t.id, t.timezone, tuple(t.scan_times), t.horizon_days) for t in rows]

    async def _load_watch_rows(
        self, s: AsyncSession, tenant_ids: tuple[int, ...]
    ) -> list[WatchRow]:
        rows = await s.execute(
            select(
                TenantHotel.tenant_id, TenantHotel.hotel_id, Tenant.horizon_days, Tenant.timezone
            )
            .join(Tenant, Tenant.id == TenantHotel.tenant_id)
            .where(TenantHotel.active.is_(True), TenantHotel.tenant_id.in_(tenant_ids))
        )
        return [WatchRow(r[0], r[1], r[2], r[3]) for r in rows]

    async def tick(self) -> TickReport:
        report = TickReport()
        now = self._clock.now()
        async with self._sf() as s:
            repo = ScanRunRepository(s)
            tenants = await self._load_tenants(s)
            for trigger in compute_triggers(tenants, now, self._lookback):
                plans = build_hotel_plans(
                    await self._load_watch_rows(s, trigger.tenant_ids), trigger.at
                )
                if not plans:
                    continue
                run = await repo.create_run(trigger.key, trigger.at, plans)
                if run is None:
                    continue
                await s.commit()
                for plan in plans:
                    await self._queue.enqueue_probe(run.id, plan.hotel_id)
                RUNS_CREATED.inc()
                QUEUE_DEPTH.set(len(plans))
                report.created_runs.append(run.id)
                log.info("scan_run_created", run_id=run.id, trigger=trigger.key, jobs=len(plans))

            for run_id, hotel_id in await repo.stale_queued_jobs(now - self._stale_after):
                await self._queue.enqueue_probe(run_id, hotel_id)
                report.reenqueued += 1

            report.expired_runs = await repo.expire_runs(self._deadline, now)
            await s.commit()
            if report.expired_runs:
                log.warning("scan_runs_expired", run_ids=report.expired_runs)
                enqueue_analytics = getattr(self._queue, "enqueue_analytics", None)
                if enqueue_analytics is not None:
                    for run_id in report.expired_runs:
                        await enqueue_analytics(run_id)

            total, blocked = await repo.probe_stats_since(now - timedelta(minutes=15))
            msg = block_rate_alert(total, blocked)
            if msg and self._throttle.should_send("block_rate"):
                await self._alerter.send(msg)
                report.alerts.append(msg)

            today = now.date()
            if self._partitions_checked_on != today:
                conn = await s.connection()
                created = await ensure_room_snapshot_partitions(conn, today, months=3)
                await s.commit()
                self._partitions_checked_on = today
                if created:
                    log.info("partitions_created", names=created)
        return report

    async def run_forever(self, interval_seconds: float = 60.0) -> None:
        log.info("scheduler_started", interval=interval_seconds)
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler_tick_failed")
            await asyncio.sleep(interval_seconds)
