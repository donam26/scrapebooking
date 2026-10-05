"""Giới hạn tần suất theo cửa sổ cố định: Redis khi có (chung mọi tiến trình API), không thì bộ nhớ
(test, một tiến trình). Dùng cho đăng nhập, quên mật khẩu, gửi thử email…"""

import time
from collections.abc import Callable
from typing import Any


class WindowThrottle:
    def __init__(
        self, limit: int, window_seconds: int, prefix: str, now: Callable[[], float] = time.time
    ) -> None:
        self._limit = max(1, limit)
        self._window = max(1, window_seconds)
        self._prefix = prefix
        self._now = now
        self._memory: dict[tuple[str, int], int] = {}

    @property
    def retry_after(self) -> int:
        return self._window

    async def hit(self, key: str, redis: Any | None = None) -> bool:
        """Ghi nhận một lần dùng của `key`; False khi đã vượt giới hạn trong cửa sổ hiện tại."""
        window = int(self._now() // self._window)
        if redis is not None:
            rkey = f"throttle:{self._prefix}:{key}:{window}"
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(rkey)
                pipe.expire(rkey, self._window * 2)
                count = int((await pipe.execute())[0])
        else:
            self._memory = {k: v for k, v in self._memory.items() if k[1] >= window}
            count = self._memory.get((key, window), 0) + 1
            self._memory[(key, window)] = count
        return count <= self._limit
