"""Dựng collector theo kênh. Mỗi kênh có module `app.collector.<kênh>.collector` với hàm
`build(deps: CollectorDeps) -> ChannelCollector`."""

import importlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.clock import Clock
from app.collector.base import Collector, ListingVerifier
from app.collector.proxy import ProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import SessionListener


class RequestBudget(Protocol):
    """Ngân sách request toàn hệ thống của một kênh (Redis, dùng chung giữa các worker)."""

    async def acquire(self) -> None: ...


class NoBudget:
    async def acquire(self) -> None:
        return None


@dataclass
class CollectorDeps:
    proxy_provider: ProxyProvider
    clock: Clock
    limiter: RateLimiter  # giãn cách giữa hai request cùng session
    currency: str  # SCAN_CURRENCY, mặc định "VND": kênh không ép được thì probe báo lỗi
    headless: bool
    session_max_age: timedelta
    session_max_requests: int
    session_listener: SessionListener | None = None
    budget: RequestBudget = NoBudget()
    country: str = "vn"  # nước của proxy / điểm bán (POS)


class ChannelCollector(Collector, ListingVerifier, Protocol):
    async def close(self) -> None: ...


def build_collector(channel: str, deps: CollectorDeps) -> ChannelCollector:
    module = importlib.import_module(f"app.collector.{channel}.collector")
    collector: ChannelCollector = module.build(deps)
    return collector
