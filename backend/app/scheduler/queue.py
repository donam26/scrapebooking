from typing import Protocol

from arq.connections import ArqRedis, RedisSettings, create_pool


class JobQueue(Protocol):
    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None: ...


def probe_job_id(scan_run_id: int, hotel_id: int) -> str:
    return f"probe:{scan_run_id}:{hotel_id}"


class ArqJobQueue:
    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    @classmethod
    async def connect(cls, redis_url: str) -> "ArqJobQueue":
        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None:
        # _job_id trùng thì arq bỏ qua: đây là chốt idempotent ở tầng hàng đợi.
        await self._redis.enqueue_job(
            "probe_hotel", scan_run_id, hotel_id, _job_id=probe_job_id(scan_run_id, hotel_id)
        )

    async def enqueue_analytics(self, scan_run_id: int) -> None:
        await self._redis.enqueue_job(
            "run_analytics", scan_run_id, _job_id=f"analytics:{scan_run_id}"
        )

    async def enqueue_insight(self, tenant_id: int, trigger: str, request_key: str) -> None:
        await self._redis.enqueue_job(
            "generate_insight", tenant_id, trigger, _job_id=f"insight:{tenant_id}:{request_key}"
        )

    async def close(self) -> None:
        await self._redis.aclose()
