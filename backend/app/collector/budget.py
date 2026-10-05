"""Ngân sách request toàn hệ thống theo kênh (D9).

Cửa sổ cố định 1 phút trong Redis, dùng chung giữa mọi worker của kênh; vượt ngân sách thì chờ sang
phút kế tiếp. Nằm trên rate limiter theo session."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class RedisRequestBudget:
    def __init__(
        self,
        redis: Any,
        channel: str,
        per_minute: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._r = redis
        self._channel = channel
        self._limit = max(1, per_minute)
        self._sleep = sleep
        self._now = now

    async def acquire(self) -> None:
        while True:
            now = self._now()
            window = int(now // 60)
            key = f"budget:{self._channel}:{window}"
            # INCR + EXPIRE cùng một transaction: chết giữa chừng không để lại khoá không hạn.
            async with self._r.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 120)
                count = int((await pipe.execute())[0])
            if count <= self._limit:
                return
            await self._sleep((window + 1) * 60 - now + 0.05)
