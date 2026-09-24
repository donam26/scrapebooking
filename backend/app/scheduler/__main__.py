import asyncio
from datetime import timedelta

from app.clock import SystemClock
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging
from app.ops.alerts import TelegramAlerter
from app.ops.metrics import start_metrics_server
from app.scheduler.queue import ArqJobQueue
from app.scheduler.service import SchedulerService


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    engine = make_engine(settings.database_url)
    queue = await ArqJobQueue.connect(settings.redis_url)
    service = SchedulerService(
        session_factory=make_session_factory(engine),
        queue=queue,
        clock=SystemClock(),
        deadline=timedelta(minutes=settings.run_deadline_minutes),
        alerter=TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id),
    )
    try:
        await service.run_forever()
    finally:
        await queue.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
