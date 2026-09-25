from typing import Protocol

from arq.connections import ArqRedis, RedisSettings, create_pool
from pydantic import ValidationError

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

# Mỗi worker một hàng đợi riêng: worker arq lấy mọi job trong hàng đợi nó nghe, job của hàm nó
# không có sẽ bị bỏ ("function not found") thay vì để worker kia xử lý.
COLLECTOR_QUEUE = "arq:queue:collector"  # probe_hotel (worker)
JOBS_QUEUE = "arq:queue:jobs"  # run_analytics, generate_insight, cron (jobs)


def worker_redis_settings() -> RedisSettings:
    """Giá trị cho `redis_settings` của lớp settings arq.

    arq lấy tham số Worker qua `WorkerSettings.__dict__` (không gọi descriptor/property), nên
    phải là RedisSettings thật lúc import. Thiếu env (test/công cụ chỉ import module) thì dùng mặc
    định; tiến trình worker thật vẫn fail rõ ở `startup` vì get_settings() cần đủ env.
    """
    try:
        return RedisSettings.from_dsn(get_settings().redis_url)
    except ValidationError as exc:
        # Worker thật sẽ báo lỗi Redis trước lỗi thiếu env: ghi rõ nguyên nhân gốc.
        log.warning("settings_invalid_using_default_redis", error=str(exc))
        return RedisSettings()


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
            "probe_hotel",
            scan_run_id,
            hotel_id,
            _job_id=probe_job_id(scan_run_id, hotel_id),
            _queue_name=COLLECTOR_QUEUE,
        )

    async def enqueue_analytics(self, scan_run_id: int) -> None:
        await self._redis.enqueue_job(
            "run_analytics",
            scan_run_id,
            _job_id=f"analytics:{scan_run_id}",
            _queue_name=JOBS_QUEUE,
        )

    async def enqueue_insight(
        self, tenant_id: int, trigger: str, request_key: str, attempt: int = 0
    ) -> None:
        # arq bỏ qua _job_id trùng khi kết quả lần trước còn lưu: lần thử lại mang số lần thử.
        job_id = f"insight:{tenant_id}:{request_key}" + (f":a{attempt}" if attempt else "")
        await self._redis.enqueue_job(
            "generate_insight",
            tenant_id,
            trigger,
            request_key,
            _job_id=job_id,
            _queue_name=JOBS_QUEUE,
        )

    async def close(self) -> None:
        await self._redis.aclose()
