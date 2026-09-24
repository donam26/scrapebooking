"""Fixture dùng chung cho test API: app FastAPI với DB test, queue giả, settings test."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings


class FakeQueue:
    def __init__(self) -> None:
        self.insights: list[tuple[int, str, str]] = []
        self.analytics: list[int] = []
        self.probes: list[tuple[int, int]] = []

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None:
        self.probes.append((scan_run_id, hotel_id))

    async def enqueue_insight(self, tenant_id: int, trigger: str, request_key: str) -> None:
        self.insights.append((tenant_id, trigger, request_key))

    async def enqueue_analytics(self, scan_run_id: int) -> None:
        self.analytics.append(scan_run_id)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="x",
        redis_url="x",
        proxy_url_template="x",
        jwt_secret="test-secret",
    )


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
async def client(
    db: AsyncSession, settings: Settings, queue: FakeQueue
) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    app = create_app(settings=settings, session_factory=factory, queue=queue)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
