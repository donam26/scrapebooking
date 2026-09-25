"""Worker `jobs` (arq): analytics sau mỗi scan run, insight hằng ngày/theo yêu cầu,
poll Batch API, backup đêm, dọn partition. Tách khỏi worker collector để không chặn probe."""

from datetime import UTC, date, datetime
from typing import Any

from arq import cron
from sqlalchemy import func, select

from app.analytics.service import AnalyticsService
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Insight, Tenant
from app.db.partitions import drop_room_snapshot_partitions_older_than
from app.insight.service import InsightService, build_insight_client, daily_due_today
from app.logging import configure_logging, get_logger
from app.ops.alerts import LogAlerter
from app.ops.backup import run_backup
from app.ops.metrics import start_metrics_server
from app.scheduler.queue import JOBS_QUEUE, ArqJobQueue, worker_redis_settings

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    ctx["settings"] = settings
    ctx["engine"] = make_engine(settings.database_url)
    ctx["session_factory"] = make_session_factory(ctx["engine"])
    ctx["client"] = build_insight_client(settings)
    ctx["queue"] = await ArqJobQueue.connect(settings.redis_url)
    ctx["alerter"] = LogAlerter()
    log.info("jobs_worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["queue"].close()
    await ctx["engine"].dispose()


async def run_analytics(ctx: dict[str, Any], scan_run_id: int) -> dict[str, int]:
    settings = ctx["settings"]
    async with ctx["session_factory"]() as s:
        svc = AnalyticsService(
            s,
            low_stock_threshold=settings.low_stock_threshold,
            price_change_threshold_pct=settings.price_change_threshold_pct,
        )
        report = await svc.run(scan_run_id)
        await s.commit()
    return {"hotel_dates": report.hotel_dates, "events": report.events, "metrics": report.metrics}


async def analytics_catch_up(ctx: dict[str, Any]) -> int:
    """Cron: chạy analytics cho run đã chốt mà chưa được tính (worker restart, lỗi tạm)."""
    async with ctx["session_factory"]() as s:
        pending = await AnalyticsService(s).pending_run_ids()
    for run_id in pending:
        await ctx["queue"].enqueue_analytics(run_id)
    return len(pending)


async def generate_insight(
    ctx: dict[str, Any], tenant_id: int, trigger: str, request_key: str | None = None
) -> dict[str, Any]:
    settings = ctx["settings"]
    use_batch = trigger == "daily" and settings.insight_use_batch
    async with ctx["session_factory"]() as s:
        svc = InsightService(s, client=ctx["client"], settings=settings)
        row = await svc.generate(tenant_id, trigger, use_batch=use_batch, request_key=request_key)
        await s.commit()
        if row.status == "failed":
            await ctx["alerter"].send(f"⚠️ Insight tenant {tenant_id} failed: {row.error}")
        return {"insight_id": row.id, "status": row.status}


MAX_DAILY_FAILURES = 2


async def select_daily_dispatch(session: Any, now: datetime) -> list[tuple[int, str, int]]:
    """(tenant, request_key, số lần đã thất bại hôm nay) cho tenant đã qua insight_hour hôm nay
    mà chưa có bản tin daily của ngày đó (đang chờ/hoàn tất), và chưa thất bại quá
    MAX_DAILY_FAILURES lần. Có catch-up: jobs worker tắt đúng giờ thì lần cron sau vẫn đẩy."""
    tenants = list((await session.execute(select(Tenant).where(Tenant.active.is_(True)))).scalars())
    out: list[tuple[int, str, int]] = []
    for d in daily_due_today(tenants, now):
        day = date.fromisoformat(d.request_key.split(":", 1)[1])
        rows = await session.execute(
            select(Insight.status, func.count())
            .where(
                Insight.tenant_id == d.tenant_id,
                Insight.trigger == "daily",
                Insight.period_start == day,
            )
            .group_by(Insight.status)
        )
        by_status = {r[0]: r[1] for r in rows}
        if any(by_status.get(st) for st in ("completed", "batch_pending", "pending")):
            continue
        failures = by_status.get("failed", 0)
        if failures >= MAX_DAILY_FAILURES:
            continue
        out.append((d.tenant_id, d.request_key, failures))
    return out


async def dispatch_daily_insights(ctx: dict[str, Any]) -> int:
    """Cron mỗi 5 phút: đẩy job daily cho tenant đã qua insight_hour và chưa có bản tin hôm nay."""
    async with ctx["session_factory"]() as s:
        due = await select_daily_dispatch(s, datetime.now(tz=UTC))
    for tenant_id, key, attempt in due:
        await ctx["queue"].enqueue_insight(tenant_id, "daily", key, attempt=attempt)
    return len(due)


async def poll_insight_batches(ctx: dict[str, Any]) -> int:
    async with ctx["session_factory"]() as s:
        svc = InsightService(s, client=ctx["client"], settings=ctx["settings"])
        n = await svc.poll_batches()
        await s.commit()
    return n


async def nightly_backup(ctx: dict[str, Any]) -> str:
    try:
        key, deleted = await run_backup(ctx["settings"])
    except Exception as exc:  # noqa: BLE001
        log.exception("backup_failed")
        await ctx["alerter"].send(f"⚠️ Postgres backup failed: {exc}")
        raise
    log.info("backup_done", key=key, deleted=len(deleted))
    return key


async def prune_partitions(ctx: dict[str, Any]) -> list[str]:
    async with ctx["session_factory"]() as s:
        conn = await s.connection()
        dropped = await drop_room_snapshot_partitions_older_than(
            conn, keep_months=24, today=datetime.now(tz=UTC).date()
        )
        await s.commit()
    if dropped:
        log.info("partitions_dropped", names=dropped)
    return dropped


class JobsWorkerSettings:
    functions = [run_analytics, generate_insight]
    cron_jobs = [
        cron(dispatch_daily_insights, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(poll_insight_batches, minute={2, 12, 22, 32, 42, 52}),
        cron(analytics_catch_up, minute={7, 37}),
        cron(nightly_backup, hour={19}, minute={30}),  # 02:30 giờ Việt Nam
        cron(prune_partitions, day={1}, hour={20}, minute={0}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = worker_redis_settings()
    queue_name = JOBS_QUEUE
    max_jobs = 2
    job_timeout = 1800
    max_tries = 2
    keep_result = 3600
