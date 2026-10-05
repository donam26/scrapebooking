import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.clock import FixedClock
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import FetchResponse
from app.collector.mytour.api import app_hash
from app.collector.mytour.collector import HttpMethod, MytourCollector
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import ScrapeSession
from app.domain.models import DemandKind, ListingQuery, ListingRef, ProbeMethod, ProbeStatus
from tests.fakes import no_sleep

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mytour"
NOW = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)
CHECKIN = date(2026, 10, 15)
LISTING = ListingRef(
    hotel_id=7,
    channel="mytour",
    listing_key="23812",
    url="https://mytour.vn/khach-san/23812-sol-by-melia-phu-quoc.html",
    country_code="vn",
    external_id="23812",
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def ok(text: str) -> FetchResponse:
    return FetchResponse(status=200, text=text, url="https://apis.tripi.vn/x", elapsed_ms=5)


class ScriptedTransport:
    def __init__(self, *responses: FetchResponse | Exception) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str], Any, Any]] = []
        self.sessions: list[str] = []
        self.closed: list[str] = []

    async def send(
        self,
        session: ScrapeSession,
        method: HttpMethod,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> FetchResponse:
        self.calls.append((method, url, headers, json_body, params))
        self.sessions.append(session.id)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self, session_id: str) -> None:
        self.closed.append(session_id)

    async def close_all(self) -> None:
        return None


class CountingBudget:
    def __init__(self) -> None:
        self.acquired = 0

    async def acquire(self) -> None:
        self.acquired += 1


def build(
    transport: ScriptedTransport, budget: CountingBudget | None = None, currency: str = "VND"
) -> MytourCollector:
    deps = CollectorDeps(
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        clock=FixedClock(NOW),
        limiter=RateLimiter(min_interval=0, jitter=0, sleep=no_sleep),
        currency=currency,
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=100,
        budget=budget or CountingBudget(),
    )
    return MytourCollector(deps, transport=transport, backoff=no_sleep, max_polls=3)


async def test_probe_polls_until_completed() -> None:
    transport = ScriptedTransport(
        ok(fixture("availability_pending.json")),
        ok(fixture("availability_sol_by_melia_1n.json")),
    )
    budget = CountingBudget()
    result = await build(transport, budget).probe(LISTING, CHECKIN, 1, 2)

    assert result.status == ProbeStatus.OK
    assert result.method == ProbeMethod.API
    assert result.external_id == "23812"
    assert result.checkout == date(2026, 10, 16)
    assert len(result.offers) == 13
    assert result.raw_html == fixture("availability_sol_by_melia_1n.json")
    [signal] = result.demand_signals
    assert signal.kind == DemandKind.LAST_BOOKED_MINUTES
    assert signal.value == 3735  # NOW - lastBookedTime, theo đồng hồ của deps
    assert budget.acquired == 2
    method, url, headers, body, _ = transport.calls[0]
    assert (method, url) == ("POST", "https://apis.tripi.vn/hotels/v3/rooms/availability")
    assert body["hotelId"] == 23812 and body["checkIn"] == "15-10-2026"
    assert headers["appHash"] == app_hash(NOW.timestamp())
    assert headers["currency"] == "VND"
    assert transport.calls[0][2]["deviceId"] == transport.calls[1][2]["deviceId"]


async def test_probe_gives_up_when_never_completed() -> None:
    pending = ok(fixture("availability_pending.json"))
    result = await build(ScriptedTransport(pending, pending, pending)).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "incomplete after 3 polls"


async def test_probe_blocked_retries_on_new_session_then_reports_blocked() -> None:
    challenge = FetchResponse(status=403, text="<html>cf</html>", url="x", elapsed_ms=1)
    transport = ScriptedTransport(challenge, challenge)
    result = await build(transport).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    assert transport.sessions[0] != transport.sessions[1]
    assert transport.closed == transport.sessions


async def test_probe_empty_result_is_sold_out_when_hotel_exists() -> None:
    transport = ScriptedTransport(
        ok(fixture("availability_empty.json")), ok(fixture("detail_sol_by_melia.json"))
    )
    result = await build(transport).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.SOLD_OUT
    assert transport.calls[1][1].endswith("/v3/hotels/detail")


async def test_probe_empty_result_for_unknown_hotel_is_not_found() -> None:
    transport = ScriptedTransport(
        ok(fixture("availability_empty.json")), ok(fixture("detail_not_found.json"))
    )
    result = await build(transport).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "not_found"


async def test_probe_api_error_code() -> None:
    bad_hash = ok('{"code":3004,"message":"Hash không tồn tại"}')
    result = await build(ScriptedTransport(bad_hash)).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "api 3004: Hash không tồn tại"


async def test_probe_currency_mismatch() -> None:
    payload = json.loads(fixture("availability_rex_2n.json"))
    for room in payload["data"]["items"]:
        for rate in room["rates"]:
            rate["formattedPrice"] = "155 USD"
    result = await build(ScriptedTransport(ok(json.dumps(payload)))).probe(LISTING, CHECKIN, 2, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "currency_mismatch:USD"


async def test_probe_transport_error_retries_once() -> None:
    transport = ScriptedTransport(
        TimeoutError("slow proxy"), ok(fixture("availability_sol_by_melia_1n.json"))
    )
    result = await build(transport).probe(LISTING, CHECKIN, 1, 2)
    assert result.status == ProbeStatus.OK


async def test_calendar_is_unsupported() -> None:
    result = await build(ScriptedTransport()).fetch_calendar(LISTING, CHECKIN, 30, 2)
    assert not result.ok and result.error == "unsupported"


async def test_verify_returns_identity() -> None:
    transport = ScriptedTransport(ok(fixture("detail_sol_by_melia.json")))
    identity = await build(transport).verify(LISTING)
    assert identity.external_id == "23812"
    assert identity.name == "SOL By Melia Phu Quoc"
    assert transport.calls[0][3] == {"hotelId": 23812}


async def test_verify_unknown_hotel_raises_not_found() -> None:
    with pytest.raises(ListingNotFound):
        await build(ScriptedTransport(ok(fixture("detail_not_found.json")))).verify(LISTING)


async def test_verify_blocked_raises_blocked() -> None:
    blocked = FetchResponse(status=429, text="", url="x", elapsed_ms=1)
    with pytest.raises(ListingBlocked):
        await build(ScriptedTransport(blocked)).verify(LISTING)


async def test_suggest_scores_candidates() -> None:
    transport = ScriptedTransport(ok(fixture("suggest_melia_vinpearl.json")))
    [candidate] = await build(transport).suggest(
        ListingQuery(name="Melia Vinpearl Phu Quoc", lat=10.3553, lng=103.8443)
    )
    assert candidate.channel == "mytour"
    assert candidate.listing_key == "40668"
    assert candidate.url == "https://mytour.vn/khach-san/40668-melia-vinpearl-phu-quoc.html"
    assert candidate.score > 0.9
    method, url, _, _, params = transport.calls[0]
    assert method == "GET" and url.endswith("/v3/suggestions/auto-complete")
    assert params == {"term": "Melia Vinpearl Phu Quoc"}
