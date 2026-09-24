import asyncio
import random
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Giữ khoảng cách tối thiểu giữa hai request cùng key (key = session id)."""

    def __init__(
        self,
        min_interval: float,
        jitter: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._min = min_interval
        self._jitter = jitter
        self._sleep = sleep
        self._now = monotonic
        self._rng = rng
        self._last: dict[str, float] = {}

    async def wait(self, key: str) -> None:
        last = self._last.get(key)
        if last is not None:
            due = last + self._min + self._rng() * self._jitter
            remaining = due - self._now()
            if remaining > 0:
                await self._sleep(remaining)
        self._last[key] = self._now()
