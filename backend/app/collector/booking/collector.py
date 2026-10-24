"""Collector Booking.com: probe/calendar qua HybridCollector, verify trang khách sạn, trang kết quả
tìm kiếm cho thị trường toàn thành phố."""

from datetime import date
from typing import Any

from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.booking.browser import BrowserCollector
from app.collector.booking.calendar import GRAPHQL_URL
from app.collector.booking.hybrid import HybridCollector
from app.collector.booking.identity import parse_identity
from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.selectors import extract_csrf_token
from app.collector.factory import CollectorDeps
from app.collector.fetch import CurlFetcher, FetchOutcome
from app.collector.session import ScrapeSession, SessionManager
from app.domain.models import (
    CalendarResult,
    ListingIdentity,
    ListingRef,
    ProbeResult,
)
from app.logging import get_logger
from app.marketscan.graphql import search_headers

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
        self, listing: ListingRef, start: date, days: int, adults: int, rooms: int = 1
    ) -> CalendarResult:
        return await self._hybrid.fetch_calendar(listing, start, days, adults, rooms)

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

    async def _retire(self, session: ScrapeSession) -> None:
        await self._sessions.retire(session, reason="blocked")
        await self._fetcher.close(session.id)

    async def search_graphql(self, payload: dict[str, Any], referer: str) -> str:
        """GraphQL `FullSearch` (thị trường khu vực, app/marketscan/graphql.py): cùng session,
        proxy, ngân sách và giãn cách với probe/lịch.

        Session chưa có csrf: tải một trang lấy `b_csrf_token` (trang kết quả `referer` khi có
        tham số tìm kiếm, không thì trang chủ); vẫn không có → coi như bị chặn. Chặn thật (403/429,
        challenge) hoặc trả 200 mà không phải JSON: thu hồi session, ném ListingBlocked. HTTP lỗi
        khác (4xx đầu vào, 5xx): lỗi thường, không làm tạm dừng kênh."""
        warmup = "https://www.booking.com/"
        session = await self._sessions.get(self._deps.country, warmup)
        if not session.csrf_token:
            if "?" in referer:
                html = await self._get_page(referer, warmup, expect=SEARCH_PAGE_MARKERS)
            else:
                html = await self._get_page(warmup, warmup)
            session = await self._sessions.get(self._deps.country, warmup)
            session.csrf_token = extract_csrf_token(html)
            if not session.csrf_token:
                await self._retire(session)
                raise ListingBlocked("graphql search: no csrf token")
        await self._deps.budget.acquire()
        await self._deps.limiter.wait(session.id)
        headers = search_headers(session.csrf_token, referer)
        response = await self._fetcher.post_json(GRAPHQL_URL, payload, headers, session)
        self._sessions.mark_request(session)
        if response.outcome == FetchOutcome.BLOCKED:
            await self._retire(session)
            raise ListingBlocked(f"graphql search blocked (http {response.status})")
        if response.outcome != FetchOutcome.OK:
            raise RuntimeError(f"graphql search http {response.status}")
        if not response.text.lstrip().startswith("{"):
            await self._retire(session)  # trang challenge/HTML với mã 200
            raise ListingBlocked("graphql search: non-json body")
        return response.text

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
