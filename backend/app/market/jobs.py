"""Job của module thị trường cho worker `jobs` (đăng ký trong app/jobs/settings.py)."""

from typing import Any

from app.logging import get_logger
from app.market.occupancy_service import MAX_ATTEMPTS, OccupancyService
from app.ops.metrics import OCCUPANCY_FAILURES

log = get_logger(__name__)


async def estimate_occupancy_catch_up(ctx: dict[str, Any]) -> int:
    """Cron: ước tính công suất cho các lượt quét đã analytics mà chưa được ước tính (cũ trước).
    Mỗi lượt commit riêng để lỗi ở một lượt không làm mất các lượt khác. Lượt lỗi được thử lại
    có giới hạn (dấu `rows` âm đếm số lần, xem OccupancyService), không bị bỏ vĩnh viễn ngay."""
    done = 0
    async with ctx["session_factory"]() as s:
        svc = OccupancyService(s)
        for run_id in await svc.pending_run_ids():
            try:
                await svc.run(run_id)
                await s.commit()
                done += 1
            except Exception:  # noqa: BLE001
                log.exception("occupancy_estimate_failed", run_id=run_id)
                await s.rollback()
                attempts = await svc.mark_failed(run_id)
                await s.commit()
                OCCUPANCY_FAILURES.inc()
                log.warning(
                    "occupancy_estimate_retry",
                    run_id=run_id,
                    attempts=attempts,
                    permanent=attempts >= MAX_ATTEMPTS,
                )
    return done
