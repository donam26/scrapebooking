from datetime import UTC, datetime, timedelta

from app.clock import FixedClock
from app.collector.proxy import ProxyEndpoint, StaticProxyProvider
from app.collector.session import (
    BootstrapResult,
    ScrapeSession,
    SessionManager,
)


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[tuple[ProxyEndpoint, str]] = []

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        self.calls.append((proxy, warmup_url))
        return BootstrapResult(
            cookies={"aws-waf-token": f"tok-{len(self.calls)}"},
            user_agent="Mozilla/5.0 Chrome/128",
            csrf_token="csrf-1",
            html="<html></html>",
        )


class RecordingListener:
    def __init__(self) -> None:
        self.created: list[ScrapeSession] = []
        self.retired: list[tuple[ScrapeSession, str]] = []

    async def session_created(self, session: ScrapeSession) -> None:
        self.created.append(session)

    async def session_retired(self, session: ScrapeSession, reason: str) -> None:
        self.retired.append((session, reason))


def _manager(
    clock: FixedClock, bootstrapper: FakeBootstrapper, listener: RecordingListener | None = None
) -> SessionManager:
    return SessionManager(
        bootstrapper=bootstrapper,
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        max_age=timedelta(minutes=20),
        max_requests=3,
        clock=clock,
        listener=listener,
    )


async def test_get_creates_and_reuses_session() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    a = await mgr.get("vn", "https://www.booking.com/hotel/vn/x.html")
    b = await mgr.get("vn", "https://www.booking.com/hotel/vn/x.html")
    assert a is b
    assert len(boot.calls) == 1
    assert boot.calls[0][0].country == "vn"
    assert a.cookies["aws-waf-token"] == "tok-1"
    assert a.user_agent.startswith("Mozilla")


async def test_sessions_are_per_country() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    vn = await mgr.get("vn", "u")
    th = await mgr.get("th", "u")
    assert vn is not th
    assert len(boot.calls) == 2


async def test_session_rotates_after_max_requests() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    s1 = await mgr.get("vn", "u")
    for _ in range(3):
        mgr.mark_request(s1)
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1
    assert s2.cookies["aws-waf-token"] == "tok-2"


async def test_session_rotates_after_max_age() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    s1 = await mgr.get("vn", "u")
    clock.advance(minutes=21)
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1


async def test_retire_forces_new_session_and_notifies_listener() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    listener = RecordingListener()
    mgr = _manager(clock, boot, listener)
    s1 = await mgr.get("vn", "u")
    await mgr.retire(s1, reason="blocked")
    assert s1.retired is True
    assert s1.block_count == 1
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1
    assert [s.id for s in listener.created] == [s1.id, s2.id]
    assert listener.retired == [(s1, "blocked")]
