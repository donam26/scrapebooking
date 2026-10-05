"""Collector kênh Booking.com: probe/calendar qua HybridCollector, verify trang khách sạn, gợi ý
listing qua autocomplete.json + trang kết quả tìm kiếm."""

import json
from datetime import date
from typing import Any
from urllib.parse import urlencode

from app.collector.base import Collector, ListingBlocked, ListingNotFound
from app.collector.booking.browser import BrowserCollector
from app.collector.booking.hybrid import HybridCollector
from app.collector.booking.identity import autocomplete_hotels, first_hotel_slug, parse_identity
from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.urls import canonical_url
from app.collector.factory import CollectorDeps
from app.collector.fetch import CurlFetcher, Fetcher, FetchOutcome
from app.collector.matching import match_score, search_names
from app.collector.session import ScrapeSession, SessionBootstrapper, SessionManager
from app.domain.models import (
    CalendarResult,
    ListingCandidate,
    ListingIdentity,
    ListingQuery,
    ListingRef,
    ProbeResult,
)
from app.logging import get_logger

log = get_logger(__name__)

AUTOCOMPLETE_URL = "https://accommodations.booking.com/autocomplete.json"
# Trang kết quả tìm kiếm thật (kể cả khi 0 kết quả) có một trong các dấu hiệu này.
SEARCH_PAGE_MARKERS = ("nbResultsTotal", 'data-testid="property-card"', "properties found")


class BookingCollector:
    def __init__(
        self,
        deps: CollectorDeps,
        *,
        fetcher: Fetcher | None = None,
        bootstrapper: SessionBootstrapper | None = None,
        fallback: Collector | None = None,
    ) -> None:
        self._deps = deps
        self._fetcher: Fetcher = fetcher or CurlFetcher()
        self._sessions = SessionManager(
            bootstrapper=bootstrapper or PlaywrightBootstrapper(headless=deps.headless),
            proxy_provider=deps.proxy_provider,
            max_age=deps.session_max_age,
            max_requests=deps.session_max_requests,
            clock=deps.clock,
            listener=deps.session_listener,
            on_retire=[self._on_session_retired],
        )
        if fallback is None:
            fallback = BrowserCollector(
                deps.proxy_provider, headless=deps.headless, currency=deps.currency
            )
        self._hybrid = HybridCollector(
            sessions=self._sessions,
            fetcher=self._fetcher,
            limiter=deps.limiter,
            fallback=fallback,
            currency=deps.currency,
            budget=deps.budget,
        )

    async def _on_session_retired(self, session: ScrapeSession, reason: str) -> None:
        """Session hết hạn/bị chặn: đóng client curl_cffi của nó (không rò AsyncSession mỗi lần
        xoay), bỏ mốc giãn cách của session."""
        await self._fetcher.close(session.id)
        self._deps.limiter.forget(session.id)

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return await self._hybrid.fetch_calendar(listing, start, days, adults)

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        return await self._hybrid.probe(listing, checkin, nights, adults)

    async def _fetch(
        self, url: str, warmup_url: str, expect: tuple[str, ...] | None = None
    ) -> tuple[str, ScrapeSession]:
        """`expect`: trang 200 mà không chứa dấu hiệu nào trong đây là chặn mềm (bỏ session).
        ListingNotFound chỉ khi Booking trả 404 thật."""
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
            await self._sessions.retire(session, reason="blocked")  # hook đóng client của session
            raise ListingBlocked(url)
        if response.outcome != FetchOutcome.OK:
            raise ListingBlocked(f"http {response.status}: {url}")
        return response.text, session

    async def _get_page(
        self, url: str, warmup_url: str, expect: tuple[str, ...] | None = None
    ) -> str:
        text, _ = await self._fetch(url, warmup_url, expect)
        return text

    async def search_page(self, url: str) -> str:
        """Trang kết quả tìm kiếm (thị trường toàn thành phố, app/marketscan): cùng session, proxy,
        ngân sách và giãn cách với probe. Bị chặn (kể cả trang 200 không phải trang kết quả): thu
        hồi session, ném ListingBlocked."""
        return await self._get_page(url, "https://www.booking.com/", expect=SEARCH_PAGE_MARKERS)

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        html, session = await self._fetch(listing.url.replace(".html", ".en-gb.html"), listing.url)
        identity = parse_identity(html, listing.listing_key)
        if not identity.name and not identity.external_id:
            # 200 nhưng không có dữ liệu khách sạn: trang challenge/chặn mềm không có dấu hiệu WAF.
            # URL sai thì Booking trả 404 thật (ListingNotFound ở _fetch).
            await self._sessions.retire(session, reason="blocked")
            raise ListingBlocked(f"no hotel data: {listing.url}")
        return identity

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        from curl_cffi.requests import AsyncSession

        proxy = self._deps.proxy_provider.new_endpoint(self._deps.country)
        hotels: list[dict[str, Any]] = []
        async with AsyncSession(
            impersonate="chrome", proxies={"http": proxy.url, "https": proxy.url}, timeout=30
        ) as client:
            # Thử lần lượt các biến thể tên: "Khu nghỉ dưỡng Melia…" không ra kết quả trên Booking.
            for variant in search_names(query.name):
                await self._deps.budget.acquire()
                r = await client.post(
                    AUTOCOMPLETE_URL,
                    json={"query": variant, "language": "en-gb", "size": 5},
                    headers={
                        "Origin": "https://www.booking.com",
                        "Referer": "https://www.booking.com/",
                    },
                )
                if r.status_code != 200:
                    raise ListingBlocked(f"autocomplete http {r.status_code}")
                try:
                    hotels = autocomplete_hotels(json.loads(r.text))
                except json.JSONDecodeError as exc:
                    raise ListingBlocked(f"autocomplete invalid json: {exc.msg}") from exc
                if hotels:
                    break
        out: list[ListingCandidate] = []
        for h in hotels[:3]:
            lat, lng = h.get("latitude"), h.get("longitude")
            latlng = (float(lat), float(lng)) if lat is not None and lng is not None else None
            name = str(h.get("label1") or h.get("label") or "")
            score = match_score(
                query.name,
                name,
                (query.lat, query.lng) if query.lat is not None and query.lng is not None else None,
                latlng,
            )
            # dest_id → slug: trang kết quả tìm kiếm với dest_type=hotel chỉ có khách sạn đó.
            search_url = "https://www.booking.com/searchresults.en-gb.html?" + urlencode(
                {"dest_id": h["dest_id"], "dest_type": "hotel", "lang": "en-gb"}
            )
            try:
                slug = first_hotel_slug(
                    await self._get_page(search_url, "https://www.booking.com/")
                )
            except (ListingBlocked, ListingNotFound):
                log.warning("booking_suggest_resolve_failed", dest_id=h["dest_id"])
                continue
            if slug is None:
                continue
            out.append(
                ListingCandidate(
                    channel="booking",
                    listing_key=slug,
                    url=canonical_url(slug),
                    name=name,
                    external_id=str(h["dest_id"]),
                    address=h.get("label2"),
                    lat=latlng[0] if latlng else None,
                    lng=latlng[1] if latlng else None,
                    country_code=h.get("cc1"),
                    score=score,
                )
            )
        return sorted(out, key=lambda c: -c.score)

    async def close(self) -> None:
        close_all = getattr(self._fetcher, "close_all", None)
        if close_all is not None:
            await close_all()


def build(deps: CollectorDeps) -> BookingCollector:
    return BookingCollector(deps)


# Hằng số worker đọc theo kênh.
from app.collector.booking.selectors import PARSER_VERSION as PARSER_VERSION  # noqa: E402

DROPDOWN_CAP = 10  # dropdown "chọn số phòng" của Booking dừng ở 10
