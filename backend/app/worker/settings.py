import socket
from datetime import timedelta
from typing import Any

from arq import Retry
from arq.connections import RedisSettings

from app.clock import SystemClock
from app.collector.booking.browser import BrowserCollector
from app.collector.booking.hybrid import HybridCollector
from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.selectors import PARSER_VERSION
from app.collector.fetch import CurlFetcher
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import SessionManager
from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging, get_logger
from app.ops.alerts import TelegramAlerter
from app.ops.metrics import start_metrics_server
from app.scheduler.queue import ArqJobQueue
from app.worker.jobs import JobFailed, WorkerDeps, run_probe_hotel
from app.worker.session_listener import DbSessionListener

log = get_logger(__name__)
MAX_TRIES = 2


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    worker_id = socket.gethostname()

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    raw_store = S3RawStore(
        bucket=settings.minio_bucket,
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    await raw_store.ensure_bucket()

    proxies = StaticProxyProvider(settings.proxy_url_template)
    max_age = timedelta(minutes=settings.session_max_age_minutes)
    sessions = SessionManager(
        bootstrapper=PlaywrightBootstrapper(headless=settings.playwright_headless),
        proxy_provider=proxies,
        max_age=max_age,
        max_requests=settings.session_max_requests,
        clock=SystemClock(),
        listener=DbSessionListener(session_factory, worker_id, max_age),
    )
    fetcher = CurlFetcher()
    collector = HybridCollector(
        sessions=sessions,
        fetcher=fetcher,
        limiter=RateLimiter(settings.request_min_interval_seconds, settings.request_jitter_seconds),
        fallback=BrowserCollector(proxies, headless=settings.playwright_headless),
    )
    queue = await ArqJobQueue.connect(settings.redis_url)

    async def on_run_finished(scan_run_id: int) -> None:
        # Giai đoạn 2: khi scan run chốt, đẩy job analytics (idempotent theo scan_run_id).
        await queue.enqueue_analytics(scan_run_id)

    ctx["engine"] = engine
    ctx["fetcher"] = fetcher
    ctx["queue"] = queue
    ctx["deps"] = WorkerDeps(
        session_factory=session_factory,
        collector=collector,
        raw_store=raw_store,
        clock=SystemClock(),
        page_cap=settings.page_dropdown_cap,
        default_adults=settings.default_adults,
        parser_version=PARSER_VERSION,
        alerter=TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id),
        worker_id=worker_id,
        on_run_finished=on_run_finished,
    )
    log.info("worker_started", worker=worker_id)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["fetcher"].close_all()
    await ctx["queue"].close()
    await ctx["engine"].dispose()


RETRY_DEFER_SECONDS = 60


async def probe_hotel(ctx: dict[str, Any], scan_run_id: int, hotel_id: int) -> dict[str, int]:
    """Job arq. Lỗi nặng (JobFailed) ở lần đầu -> `Retry` để arq chạy lại sau 60s với job_try+1;
    tới lần cuối thì run_probe_hotel tự chốt scan run (không đợi hạn chót 90 phút)."""
    job_try = int(ctx.get("job_try", 1))
    final_attempt = job_try >= MAX_TRIES
    try:
        summary = await run_probe_hotel(
            ctx["deps"], scan_run_id, hotel_id, final_attempt=final_attempt
        )
    except JobFailed:
        if not final_attempt:
            raise Retry(defer=RETRY_DEFER_SECONDS) from None
        raise
    return {"probed": summary.probed, "skipped": summary.skipped, "failed": summary.failed}


class _LazyRedisSettings:
    """arq đọc `WorkerSettings.redis_settings` lúc chạy; đọc env muộn để import module không cần env
    (test và công cụ khác import được mà không cần DATABASE_URL...)."""

    def __get__(self, obj: object, owner: type | None = None) -> RedisSettings:
        return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [probe_hotel]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _LazyRedisSettings()
    max_jobs = 1  # một khách sạn một lúc mỗi tiến trình; scale bằng số tiến trình
    job_timeout = 3600
    max_tries = MAX_TRIES
    keep_result = 3600
