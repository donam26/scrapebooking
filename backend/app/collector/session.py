import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from app.clock import Clock
from app.collector.proxy import ProxyEndpoint, ProxyProvider


@dataclass(frozen=True)
class BootstrapResult:
    cookies: dict[str, str]
    user_agent: str
    csrf_token: str | None
    html: str


class SessionBootstrapper(Protocol):
    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult: ...


@dataclass
class ScrapeSession:
    id: str
    proxy: ProxyEndpoint
    cookies: dict[str, str]
    user_agent: str
    csrf_token: str | None
    created_at: datetime
    request_count: int = 0
    block_count: int = 0
    retired: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def country(self) -> str:
        return self.proxy.country


class SessionListener(Protocol):
    async def session_created(self, session: ScrapeSession) -> None: ...
    async def session_retired(self, session: ScrapeSession, reason: str) -> None: ...


class SessionManager:
    """Giữ một session còn hạn cho mỗi nước. Làm mới khi hết tuổi, hết số request,
    hoặc bị thu hồi."""

    def __init__(
        self,
        bootstrapper: SessionBootstrapper,
        proxy_provider: ProxyProvider,
        max_age: timedelta,
        max_requests: int,
        clock: Clock,
        listener: SessionListener | None = None,
    ) -> None:
        self._bootstrapper = bootstrapper
        self._proxies = proxy_provider
        self._max_age = max_age
        self._max_requests = max_requests
        self._clock = clock
        self._listener = listener
        self._sessions: dict[str, ScrapeSession] = {}

    def _expired(self, s: ScrapeSession) -> bool:
        if s.retired:
            return True
        if s.request_count >= self._max_requests:
            return True
        return self._clock.now() - s.created_at > self._max_age

    async def get(self, country: str, warmup_url: str) -> ScrapeSession:
        current = self._sessions.get(country)
        if current is not None and not self._expired(current):
            return current
        if current is not None and not current.retired:
            await self.retire(current, reason="expired")
        return await self._create(country, warmup_url)

    async def _create(self, country: str, warmup_url: str) -> ScrapeSession:
        proxy = self._proxies.new_endpoint(country)
        result = await self._bootstrapper.bootstrap(proxy, warmup_url)
        session = ScrapeSession(
            id=uuid.uuid4().hex[:16],
            proxy=proxy,
            cookies=result.cookies,
            user_agent=result.user_agent,
            csrf_token=result.csrf_token,
            created_at=self._clock.now(),
        )
        self._sessions[country] = session
        if self._listener:
            await self._listener.session_created(session)
        return session

    def mark_request(self, session: ScrapeSession) -> None:
        session.request_count += 1

    async def retire(self, session: ScrapeSession, reason: str) -> None:
        if session.retired:
            return
        session.retired = True
        if reason == "blocked":
            session.block_count += 1
        if self._sessions.get(session.country) is session:
            del self._sessions[session.country]
        if self._listener:
            await self._listener.session_retired(session, reason)

    @property
    def expires_after(self) -> timedelta:
        return self._max_age
