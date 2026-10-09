import asyncio
from datetime import timedelta

from app.clock import SystemClock
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging
from app.marketscan.scheduling import MarketScheduler
from app.ops.alerts import make_alerter
from app.ops.metrics import start_metrics_server
from app.ops.proxy_check import ProxyHealth, ProxyHealthStore, check_proxies
from app.scheduler.channel_pause import RedisChannelPauses
from app.scheduler.queue import ArqJobQueue
from app.scheduler.service import SchedulerService


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    engine = make_engine(settings.database_url)
    queue = await ArqJobQueue.connect(settings.redis_url)

    async def proxy_checker() -> list[ProxyHealth]:
        return await check_proxies(settings.proxy_templates)

    session_factory = make_session_factory(engine)
    pauses = RedisChannelPauses(queue.redis)
    market = MarketScheduler(
        session_factory,
        queue,
        list_time=settings.market_list_time,
        detail_time=settings.market_detail_time,
        inflight=settings.market_detail_inflight,
        paused=pauses.is_paused,
        max_hotels=settings.market_max_hotels,
        retention_days=settings.market_list_retention_days,
    )
    service = SchedulerService(
        session_factory=session_factory,
        queue=queue,
        clock=SystemClock(),
        deadline=timedelta(minutes=settings.run_deadline_minutes),
        alerter=make_alerter(settings),
        pauses=pauses,
        proxy_checker=proxy_checker,
        block_threshold=settings.channel_block_rate_threshold,
        block_min_probes=settings.channel_block_min_probes,
        pause_minutes=settings.channel_pause_minutes,
        market=market,
        market_deadline=timedelta(hours=settings.market_run_deadline_hours),
        proxy_health=ProxyHealthStore(queue.redis),
    )
    try:
        await service.run_forever()
    finally:
        await queue.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
