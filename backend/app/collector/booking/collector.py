"""Collector Booking.com: probe/calendar qua HybridCollector, verify trang khách sạn, trang kết quả
tìm kiếm cho thị trường toàn thành phố."""

from datetime import date

from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.booking.browser import BrowserCollector
from app.collector.booking.hybrid import HybridCollector
from app.collector.booking.identity import parse_identity
from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.factory import CollectorDeps
from app.collector.fetch import CurlFetcher, FetchOutcome
from app.collector.session import SessionManager
from app.domain.models import (
    CalendarResult,
    ListingIdentity,
    ListingRef,
    ProbeResult,
)
from app.logging import get_logger

log = get_logger(__name__)

# Trang kết quả tìm kiếm thật (kể cả khi 0 kết quả) có một trong các dấu hiệu này.
SEARCH_PAGE_MARKERS = ("nbResultsTotal", 'data-testid="property-card"', "properties found")


class BookingCollector:
    def __init__(self, deps: CollectorDeps) -> None:
        self._deps = deps
        self._sessions = SessionManager(
            bootstrapper=PlaywrightBootstrapper(headless=deps.headless),
            proxy_provider=deps.proxy_provider,
            max_age=deps.session_max_age,
            max_requests=deps.session_max_requests,
            clock=deps.clock,
            listener=deps.session_listener,
        )
        self._fetcher = CurlFetcher()
        self._hybrid = HybridCollector(
            sessions=self._sessions,
            fetcher=self._fetcher,
            limiter=deps.limiter,
            fallback=BrowserCollector(
                deps.proxy_provider, headless=deps.headless, currency=deps.currency
            ),
            currency=deps.currency,
            budget=deps.budget,
        )

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return await self._hybrid.fetch_calendar(listing, start, days, adults)

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        return await self._hybrid.probe(listing, checkin, nights, adults)

    async def _get_page(
        self, url: str, warmup_url: str, expect: tuple[str, ...] | None = None
    ) -> str:
        """`expect`: trang 200 mà không chứa dấu hiệu nào trong đây là chặn mềm (bỏ session)."""
        session = await self._sessions.get(self._deps.country, warmup_url)
        await self._deps.budget.acquire()
        await self._deps.limiter.wait(session.id)
        response = await self._fetcher.get(url, session)
        self._sessions.mark_request(session)
        if response.outcome == FetchOutcome.NOT_FOUND:
            raise ListingNotFound(url)
        soft_block = (
            expect is not None
            and response.outcome == FetchOutcome.OK
            and not any(marker in response.text for marker in expect)
        )
        if response.outcome == FetchOutcome.BLOCKED or soft_block:
            await self._sessions.retire(session, reason="blocked")
            await self._fetcher.close(session.id)
            raise ListingBlocked(url)
        if response.outcome != FetchOutcome.OK:
            raise ListingBlocked(f"http {response.status}: {url}")
        return response.text

    async def search_page(self, url: str) -> str:
        """Trang kết quả tìm kiếm (thị trường toàn thành phố, app/marketscan): cùng session, proxy,
        ngân sách và giãn cách với probe. Bị chặn (kể cả trang 200 không phải trang kết quả): thu
        hồi session, ném ListingBlocked."""
        return await self._get_page(url, "https://www.booking.com/", expect=SEARCH_PAGE_MARKERS)

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        html = await self._get_page(listing.url.replace(".html", ".en-gb.html"), listing.url)
        identity = parse_identity(html, listing.listing_key)
        if not identity.name and not identity.external_id:
            raise ListingNotFound(listing.url)
        return identity

    async def close(self) -> None:
        await self._fetcher.close_all()


def build(deps: CollectorDeps) -> BookingCollector:
    return BookingCollector(deps)


# Hằng số worker đọc theo kênh.
from app.collector.booking.selectors import PARSER_VERSION as PARSER_VERSION  # noqa: E402

DROPDOWN_CAP = 10  # dropdown "chọn số phòng" của Booking dừng ở 10
