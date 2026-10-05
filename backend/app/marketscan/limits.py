"""Trần tải phía server của thị trường toàn thành phố: kẹp cấu hình khu vực, giới hạn số lần tìm địa
điểm (gọi Booking thật) mỗi tenant mỗi phút."""

import time
from collections.abc import Callable
from typing import Any

from app.config import Settings


def clamp_config(values: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Kẹp số khách sạn quét chi tiết và ngân sách request khám phá theo trần của hệ thống."""
    out = dict(values)
    if out.get("detail_max_hotels") is not None:
        out["detail_max_hotels"] = min(int(out["detail_max_hotels"]), settings.market_max_hotels)
    if out.get("max_pages") is not None:
        out["max_pages"] = min(int(out["max_pages"]), settings.market_max_pages)
    return out


class SearchThrottle:
    """Đếm theo cửa sổ 1 phút: Redis khi có (chung mọi tiến trình API), không thì bộ nhớ."""

    def __init__(self, per_minute: int, now: Callable[[], float] = time.time) -> None:
        self._limit = max(1, per_minute)
        self._now = now
        self._memory: dict[tuple[int, int], int] = {}

    async def allow(self, tenant_id: int, redis: Any | None = None) -> bool:
        window = int(self._now() // 60)
        if redis is not None:
            key = f"throttle:market_search:{tenant_id}:{window}"
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 120)
                count = int((await pipe.execute())[0])
        else:
            self._memory = {k: v for k, v in self._memory.items() if k[1] >= window}
            count = self._memory.get((tenant_id, window), 0) + 1
            self._memory[(tenant_id, window)] = count
        return count <= self._limit
