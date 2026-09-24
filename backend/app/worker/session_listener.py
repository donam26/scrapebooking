from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.session import ScrapeSession
from app.db.models import ScrapeSessionRow
from app.ops.metrics import SESSIONS_CREATED, SESSIONS_RETIRED


class DbSessionListener:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], worker_id: str, max_age: timedelta
    ) -> None:
        self._sf = session_factory
        self._worker_id = worker_id
        self._max_age = max_age

    async def session_created(self, session: ScrapeSession) -> None:
        SESSIONS_CREATED.labels(session.country).inc()
        async with self._sf() as s:
            s.add(
                ScrapeSessionRow(
                    id=session.id,
                    worker_id=self._worker_id,
                    proxy_id=session.proxy.id,
                    proxy_country=session.country,
                    created_at=session.created_at,
                    expires_at=session.created_at + self._max_age,
                    status="active",
                )
            )
            await s.commit()

    async def session_retired(self, session: ScrapeSession, reason: str) -> None:
        SESSIONS_RETIRED.labels(reason).inc()
        async with self._sf() as s:
            await s.execute(
                update(ScrapeSessionRow)
                .where(ScrapeSessionRow.id == session.id)
                .values(
                    retired_at=datetime.now(tz=UTC),
                    status=f"retired:{reason}",
                    request_count=session.request_count,
                    block_count=session.block_count,
                )
            )
            await s.commit()
