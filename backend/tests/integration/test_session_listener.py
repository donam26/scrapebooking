from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.proxy import ProxyEndpoint
from app.collector.session import ScrapeSession
from app.db.models import ScrapeSessionRow
from app.worker.session_listener import DbSessionListener

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)


def _session() -> ScrapeSession:
    proxy = ProxyEndpoint(
        server="http://h:1",
        username="u",
        password="p",
        country="vn",
        session_id="abc",
        url="http://u:p@h:1",
    )
    return ScrapeSession(
        id="sess1", proxy=proxy, cookies={}, user_agent="ua", csrf_token=None, created_at=NOW
    )


async def test_listener_persists_created_and_retired(db: AsyncSession) -> None:
    listener = DbSessionListener(
        async_sessionmaker(db.bind, expire_on_commit=False),
        worker_id="w1",
        max_age=timedelta(minutes=20),
    )  # type: ignore[arg-type]
    s = _session()
    await listener.session_created(s)
    s.request_count = 12
    await listener.session_retired(s, "blocked")
    row = (await db.execute(select(ScrapeSessionRow))).scalar_one()
    assert row.id == "sess1" and row.worker_id == "w1" and row.proxy_id == "vn:abc"
    assert row.expires_at == NOW + timedelta(minutes=20)
    assert (
        row.status == "retired:blocked" and row.request_count == 12 and row.retired_at is not None
    )
