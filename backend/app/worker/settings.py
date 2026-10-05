"""Worker thu dữ liệu của một kênh (WORKER_CHANNEL). Mỗi kênh một hàng đợi và số tiến trình riêng
(D9): kênh chậm/bị chặn không làm chậm kênh khác."""

import importlib
import os
import socket
from datetime import timedelta
from typing import Any

from arq import Retry
from arq.worker import func

from app.clock import SystemClock
from app.collector.budget import RedisRequestBudget
from app.collector.factory import CollectorDeps, build_collector
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging, get_logger
from app.marketscan.jobs import scan_market_list
from app.ops.alerts import make_alerter
from app.ops.metrics import start_metrics_server
from app.scheduler.channel_pause import RedisChannelPauses
from app.scheduler.queue import ArqJobQueue, collector_queue, worker_redis_settings
from app.worker.jobs import (
    JobFailed,
    PermanentJobFailure,
    TierPolicy,
    WorkerDeps,
    fail_job,
    run_probe_hotel,
)
from app.worker.listing_jobs import (
    ListingJobDeps,
    ListingRetry,
    run_discover_listing,
    run_verify_listing,
)
from app.worker.session_listener import DbSessionListener

log = get_logger(__name__)
MAX_TRIES = 2
LISTING_MAX_TRIES = 3


def _channel_constants(channel: str, default_cap: int) -> tuple[str, int]:
    module = importlib.import_module(f"app.collector.{channel}.collector")
    return str(getattr(module, "PARSER_VERSION", "1")), int(
        getattr(module, "DROPDOWN_CAP", default_cap)
    )


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    channel = settings.worker_channel
    worker_id = f"{socket.gethostname()}:{channel}"

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    raw_store = S3RawStore(
        bucket=settings.minio_bucket,
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    await raw_store.ensure_bucket()

    queue = await ArqJobQueue.connect(settings.redis_url)
    max_age = timedelta(minutes=settings.session_max_age_minutes)
    collector = build_collector(
        channel,
        CollectorDeps(
            proxy_provider=StaticProxyProvider(settings.proxy_templates),
            clock=SystemClock(),
            limiter=RateLimiter(
                settings.request_min_interval_seconds, settings.request_jitter_seconds
            ),
            currency=settings.scan_currency,
            headless=settings.playwright_headless,
            session_max_age=max_age,
            session_max_requests=settings.session_max_requests,
            session_listener=DbSessionListener(session_factory, worker_id, max_age),
            budget=RedisRequestBudget(queue.redis, channel, settings.channel_budget(channel)),
        ),
    )
    parser_version, page_cap = _channel_constants(channel, settings.page_dropdown_cap)

    async def on_run_finished(scan_run_id: int) -> None:
        # Khi scan run chốt, đẩy job analytics (idempotent theo scan_run_id).
        await queue.enqueue_analytics(scan_run_id)

    ctx["engine"] = engine
    ctx["collector"] = collector
    ctx["queue"] = queue
    ctx["pauses"] = RedisChannelPauses(queue.redis)
    ctx["channel"] = channel
    ctx["deps"] = WorkerDeps(
        session_factory=session_factory,
        collector=collector,
        raw_store=raw_store,
        clock=SystemClock(),
        page_cap=page_cap,
        default_adults=settings.default_adults,
        parser_version=f"{channel}:{parser_version}",
        alerter=make_alerter(settings),
        worker_id=worker_id,
        on_run_finished=on_run_finished,
        tiers=TierPolicy(
            near_days=settings.tier_near_days,
            mid_days=settings.tier_mid_days,
            mid_max_age=timedelta(hours=settings.tier_mid_max_age_hours),
            far_max_age=timedelta(hours=settings.tier_far_max_age_hours),
        ),
    )
    ctx["listing_deps"] = ListingJobDeps(
        session_factory=session_factory,
        collector=collector,
        clock=SystemClock(),
        channel=channel,
        enqueue_discover=queue.enqueue_discover,
    )
    log.info("worker_started", worker=worker_id, channel=channel, queue=collector_queue(channel))


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["collector"].close()
    await ctx["queue"].close()
    await ctx["engine"].dispose()


RETRY_DEFER_SECONDS = 60


async def probe_hotel(ctx: dict[str, Any], scan_run_id: int, hotel_id: int) -> dict[str, int]:
    """Job arq. Lỗi nặng (JobFailed) ở lần đầu -> `Retry` để arq chạy lại sau 60s với job_try+1;
    tới lần cuối thì run_probe_hotel tự chốt scan run (không đợi hạn chót 90 phút).
    Kênh đang bị tự ngắt (D9): hoãn job tới khi hết hạn thay vì gửi thêm request bị chặn."""
    job_try = int(ctx.get("job_try", 1))
    final_attempt = job_try >= MAX_TRIES
    if await ctx["pauses"].is_paused(ctx["channel"]):
        # Không gửi thêm request vào kênh đang bị chặn: chốt job thất bại, quét bù lo phần còn lại.
        await fail_job(ctx["deps"], scan_run_id, hotel_id, "channel paused (block rate)")
        return {"probed": 0, "skipped": 0, "fresh": 0, "failed": 0}
    try:
        summary = await run_probe_hotel(
            ctx["deps"], scan_run_id, hotel_id, final_attempt=final_attempt
        )
    except JobFailed as exc:
        if not final_attempt and not isinstance(exc, PermanentJobFailure):
            raise Retry(defer=RETRY_DEFER_SECONDS) from None
        raise
    return {
        "probed": summary.probed,
        "skipped": summary.skipped,
        "fresh": summary.fresh,
        "failed": summary.failed,
    }


async def verify_listing(ctx: dict[str, Any], listing_id: int) -> str:
    final_attempt = int(ctx.get("job_try", 1)) >= LISTING_MAX_TRIES
    try:
        return await run_verify_listing(ctx["listing_deps"], listing_id, final_attempt)
    except ListingRetry:
        raise Retry(defer=RETRY_DEFER_SECONDS * 2) from None


async def discover_listing(ctx: dict[str, Any], hotel_id: int) -> str:
    final_attempt = int(ctx.get("job_try", 1)) >= LISTING_MAX_TRIES
    try:
        return await run_discover_listing(ctx["listing_deps"], hotel_id, final_attempt)
    except ListingRetry:
        raise Retry(defer=RETRY_DEFER_SECONDS * 2) from None


class WorkerSettings:
    # Số lần thử theo từng hàm: probe_hotel coi lần MAX_TRIES là lần cuối (tự chốt run), nên arq
    # phải dừng đúng ở đó; scan_market_list một lần (chuỗi đêm tự đi tiếp/bù, không chạy lại đêm).
    # scan_market_list chỉ được đẩy vào hàng đợi kênh có trang danh sách (Booking).
    functions = [
        func(probe_hotel, max_tries=MAX_TRIES),
        func(verify_listing, max_tries=LISTING_MAX_TRIES),
        func(discover_listing, max_tries=LISTING_MAX_TRIES),
        func(scan_market_list, max_tries=1),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = worker_redis_settings()
    # Đọc thẳng biến môi trường: arq lấy thuộc tính lúc import, test chỉ import module không có env.
    queue_name = collector_queue(os.environ.get("WORKER_CHANNEL", "booking"))
    max_jobs = 1  # một khách sạn một lúc mỗi tiến trình; scale bằng số tiến trình
    job_timeout = 3600
    max_tries = LISTING_MAX_TRIES
    keep_result = 3600
