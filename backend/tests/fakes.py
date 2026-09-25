from collections import deque
from datetime import date
from decimal import Decimal
from typing import Any

from app.collector.fetch import FetchResponse
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult, ScrapeSession
from app.domain.models import PageOutcome, ParsedPage, RatePlan, RoomOffer


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[tuple[ProxyEndpoint, str]] = []

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        self.calls.append((proxy, warmup_url))
        return BootstrapResult(
            cookies={"aws-waf-token": f"tok-{len(self.calls)}"},
            user_agent="Mozilla/5.0 Chrome/128",
            csrf_token=f"csrf-{len(self.calls)}",
            html="<html></html>",
        )


class FakeFetcher:
    """Trả lần lượt các FetchResponse hoặc ném Exception theo hàng đợi."""

    def __init__(self, *responses: FetchResponse | Exception) -> None:
        self.queue: deque[FetchResponse | Exception] = deque(responses)
        self.get_calls: list[tuple[str, str]] = []  # (url, session_id)
        self.post_calls: list[tuple[str, dict[str, Any], dict[str, str], str]] = []
        self.closed: list[str] = []

    def _next(self) -> FetchResponse:
        item = self.queue.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url: str, session: ScrapeSession) -> FetchResponse:
        self.get_calls.append((url, session.id))
        return self._next()

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse:
        self.post_calls.append((url, payload, headers, session.id))
        return self._next()

    async def close(self, session_id: str) -> None:
        self.closed.append(session_id)


def resp(status: int, text: str) -> FetchResponse:
    return FetchResponse(status=status, text=text, url="https://www.booking.com/x", elapsed_ms=10)


OFFER = RoomOffer(
    booking_room_id="101",
    name="Deluxe",
    max_occupancy=2,
    badge_count=2,
    dropdown_max=2,
    rates=(RatePlan("Standard", Decimal("1000000"), "VND", True, None),),
)


def fake_parser(html: str, expected_currency: str, adults: int | None = None) -> ParsedPage:
    if "ROOMS" in html:
        return ParsedPage(PageOutcome.ROOMS, "555", "Fake Hotel", "csrf-page", (OFFER,))
    if "SOLDOUT" in html:
        return ParsedPage(PageOutcome.SOLD_OUT, "555", "Fake Hotel", "csrf-page", ())
    return ParsedPage(PageOutcome.EMPTY, "555", "Fake Hotel", None, ())


async def no_sleep(_: float) -> None:
    return None


def any_date() -> date:
    return date(2026, 10, 5)
