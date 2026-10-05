"""Fixture dùng chung cho test API: app FastAPI với DB test, queue giả, settings test."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.config import Settings
from tests.fakes import FakeEmailSender


class FakeQueue:
    def __init__(self) -> None:
        self.insights: list[tuple[int, str, str]] = []
        self.analytics: list[int] = []
        self.probes: list[tuple[int, int]] = []
        self.probe_channels: list[str] = []
        self.verifies: list[tuple[int, str]] = []
        self.discovers: list[tuple[int, str]] = []

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int, channel: str) -> None:
        self.probes.append((scan_run_id, hotel_id))
        self.probe_channels.append(channel)

    async def enqueue_verify(self, listing_id: int, channel: str) -> None:
        self.verifies.append((listing_id, channel))

    async def enqueue_discover(self, hotel_id: int, channel: str) -> None:
        self.discovers.append((hotel_id, channel))

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
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
async def client(
    db: AsyncSession, settings: Settings, queue: FakeQueue, email_sender: FakeEmailSender
) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    app = create_app(settings=settings, session_factory=factory, queue=queue)
    app.state.email_sender = email_sender
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
