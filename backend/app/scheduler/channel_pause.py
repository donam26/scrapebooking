"""Tự ngắt kênh (D9): kênh bị chặn nhiều thì tạm dừng, các kênh khác chạy tiếp.

Trạng thái nằm trong Redis (có TTL) để scheduler và mọi worker cùng thấy, tự hết hạn.
"""

from datetime import datetime, timedelta
from typing import Any, Protocol


def pause_key(channel: str) -> str:
    return f"channel_paused:{channel}"


class ChannelPauses(Protocol):
    async def is_paused(self, channel: str) -> bool: ...
    async def pause(self, channel: str, minutes: int, reason: str) -> None: ...


class RedisChannelPauses:
    def __init__(self, redis: Any) -> None:
        self._r = redis

    async def is_paused(self, channel: str) -> bool:
        return bool(await self._r.exists(pause_key(channel)))

    async def pause(self, channel: str, minutes: int, reason: str) -> None:
        await self._r.set(pause_key(channel), reason, ex=minutes * 60)


class MemoryChannelPauses:
    """Cho test: dùng đồng hồ ngoài để hết hạn."""

    def __init__(self, now: Any) -> None:
        self._now = now  # callable -> datetime
        self._until: dict[str, datetime] = {}

    async def is_paused(self, channel: str) -> bool:
        until = self._until.get(channel)
        return until is not None and self._now() < until

    async def pause(self, channel: str, minutes: int, reason: str) -> None:
        self._until[channel] = self._now() + timedelta(minutes=minutes)


def should_pause(total: int, blocked: int, min_probes: int, threshold: float) -> bool:
    return total >= min_probes and blocked / total > threshold
