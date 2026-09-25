from typing import Any

import pytest
from arq.connections import RedisSettings
from arq.worker import get_kwargs

from app.config import get_settings
from app.jobs.settings import JobsWorkerSettings
from app.scheduler.queue import ArqJobQueue, worker_redis_settings
from app.worker.settings import WorkerSettings

WORKERS = [WorkerSettings, JobsWorkerSettings]


@pytest.mark.parametrize("settings_cls", WORKERS)
def test_arq_reads_real_redis_settings(settings_cls: type) -> None:
    # arq lấy tham số Worker qua `settings_cls.__dict__` (không gọi descriptor/property):
    # redis_settings phải là RedisSettings thật, nếu không worker chết ngay khi khởi động.
    kwargs = get_kwargs(settings_cls)
    assert isinstance(kwargs["redis_settings"], RedisSettings)


def test_worker_redis_settings_uses_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x@h/db")
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://u-{country}-{session}:p@h:1")
    monkeypatch.setenv("REDIS_URL", "redis://redis-test:6390/3")
    get_settings.cache_clear()
    try:
        rs = worker_redis_settings()
    finally:
        get_settings.cache_clear()
    assert (rs.host, rs.port, rs.database) == ("redis-test", 6390, 3)


class _RecordingRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.job_ids: list[str | None] = []

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((function, kwargs.get("_queue_name")))
        self.job_ids.append(kwargs.get("_job_id"))


async def test_every_enqueued_job_goes_to_a_worker_that_has_the_function() -> None:
    # Hai worker cùng nghe một hàng đợi thì job bị worker kia lấy mất ("function not found").
    queues = [get_kwargs(w).get("queue_name") for w in WORKERS]
    assert len(set(queues)) == len(WORKERS)

    redis = _RecordingRedis()
    queue = ArqJobQueue(redis)  # type: ignore[arg-type]
    await queue.enqueue_probe(1, 2)
    await queue.enqueue_analytics(1)
    await queue.enqueue_insight(1, "on_demand", "req1")

    by_queue = {get_kwargs(w).get("queue_name"): {f.__name__ for f in w.functions} for w in WORKERS}
    for function, queue_name in redis.calls:
        assert queue_name in by_queue, (function, queue_name)
        assert function in by_queue[queue_name], (function, queue_name)


async def test_insight_retry_gets_a_new_job_id() -> None:
    # arq bỏ qua job trùng _job_id khi kết quả lần trước còn lưu (keep_result): lần gửi lại sau
    # thất bại phải có id khác, nếu không bản tin hằng ngày không được thử lại.
    redis = _RecordingRedis()
    queue = ArqJobQueue(redis)  # type: ignore[arg-type]
    await queue.enqueue_insight(1, "daily", "daily:2026-10-04")
    await queue.enqueue_insight(1, "daily", "daily:2026-10-04", attempt=1)
    assert redis.job_ids[0] == "insight:1:daily:2026-10-04"
    assert redis.job_ids[1] != redis.job_ids[0]
