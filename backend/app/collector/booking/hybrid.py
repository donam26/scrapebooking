import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import date

from app.collector.base import Collector
from app.collector.booking.calendar import (
    GRAPHQL_URL,
    build_calendar_request,
    calendar_headers,
    parse_calendar_response,
)
from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.results import failed_result, probe_result_from_page
from app.collector.booking.selectors import dates_dropped, shown_other_checkin
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.fetch import Fetcher, FetchOutcome
from app.collector.ratelimit import RateLimiter
from app.collector.session import ScrapeSession, SessionManager
from app.domain.models import (
    CalendarResult,
    HotelRef,
    PageOutcome,
    ParsedPage,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
)
from app.logging import get_logger

log = get_logger(__name__)

Parser = Callable[[str, str, int | None], ParsedPage]  # (html, tiền tệ, số người lớn)


class HybridCollector:
    """Session lai: cookie từ Playwright, tải trang bằng curl_cffi.

    Khi bị chặn: thu hồi session, thử lại bằng session mới tối đa `http_retries` lần,
    rồi chuyển sang `fallback` (BrowserCollector). Trang rỗng không có dấu hiệu chặn cũng
    chuyển sang fallback để trình duyệt thật quyết định, nhưng không thu hồi session.
    """

    def __init__(
        self,
        sessions: SessionManager,
        fetcher: Fetcher,
        limiter: RateLimiter,
        fallback: Collector | None,
        parser: Parser = parse_hotel_page,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        http_retries: int = 1,
        backoff_seconds: float = 3.0,
        transient_retries: int = 1,
    ) -> None:
        self._sessions = sessions
        self._fetcher = fetcher
        self._limiter = limiter
        self._fallback = fallback
        self._parser = parser
        self._backoff = backoff
        self._http_retries = http_retries
        self._backoff_seconds = backoff_seconds
        self._transient_retries = transient_retries

    async def _retire_blocked(self, session: ScrapeSession) -> None:
        await self._sessions.retire(session, reason="blocked")
        await self._fetcher.close(session.id)

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        session = await self._sessions.get(hotel.country_code, hotel.canonical_url)
        await self._limiter.wait(session.id)
        payload = build_calendar_request(hotel.country_code, hotel.pagename, start, days, adults)
        headers = calendar_headers(session.csrf_token, referer=hotel.canonical_url)
        try:
            response = await self._fetcher.post_json(GRAPHQL_URL, payload, headers, session)
        except Exception as exc:  # noqa: BLE001
            return CalendarResult(ok=False, error=f"transport: {type(exc).__name__}: {exc}")
        self._sessions.mark_request(session)
        if response.outcome == FetchOutcome.BLOCKED:
            await self._retire_blocked(session)
            return CalendarResult(ok=False, error="blocked")
        if response.outcome != FetchOutcome.OK:
            return CalendarResult(ok=False, error=f"http {response.status}")
        return parse_calendar_response(response.text)

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        currency = currency_for(hotel.country_code)
        url = build_hotel_url(hotel, checkin, nights, adults, currency)
        attempts = 0
        transient = 0  # lỗi tạm thời (5xx, mạng): thử lại trên cùng session
        last_status: int | None = None
        last_session: str | None = None
        while True:
            session = await self._sessions.get(hotel.country_code, hotel.canonical_url)
            last_session = session.id
            await self._limiter.wait(session.id)
            t0 = time.monotonic()
            try:
                response = await self._fetcher.get(url, session)
            except Exception as exc:  # noqa: BLE001
                if transient < self._transient_retries:
                    transient += 1
                    log.info("probe_transport_retry", hotel=hotel.id, error=type(exc).__name__)
                    await self._backoff(self._backoff_seconds)
                    continue
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.HTTP,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error=f"transport: {type(exc).__name__}: {exc}",
                    session_id=session.id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            self._sessions.mark_request(session)
            duration_ms = int((time.monotonic() - t0) * 1000)
            last_status = response.status
            outcome = response.outcome
            if outcome == FetchOutcome.OK and dates_dropped(response.text):
                log.warning("probe_dates_dropped", hotel=hotel.id, checkin=str(checkin))
                outcome = FetchOutcome.BLOCKED
            other = (
                shown_other_checkin(response.text, checkin) if outcome == FetchOutcome.OK else None
            )
            if other is not None:
                # Không phải chặn (không đổi session), nhưng không được ghi dữ liệu sang ngày sai.
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.HTTP,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error=f"booking showed other dates: checkin {other}",
                    http_status=response.status,
                    session_id=session.id,
                    duration_ms=duration_ms,
                )
            if outcome == FetchOutcome.BLOCKED:
                log.warning(
                    "probe_blocked",
                    hotel=hotel.id,
                    checkin=str(checkin),
                    status=response.status,
                    attempt=attempts,
                )
                await self._retire_blocked(session)
                if attempts < self._http_retries:
                    attempts += 1
                    await self._backoff(self._backoff_seconds * attempts)
                    continue
                return await self._fallback_or_blocked(
                    hotel, checkin, nights, adults, last_status, last_session
                )
            if outcome == FetchOutcome.NOT_FOUND:
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.HTTP,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error="not_found",
                    http_status=404,
                    session_id=session.id,
                    duration_ms=duration_ms,
                )
            if outcome == FetchOutcome.ERROR:
                if response.status >= 500 and transient < self._transient_retries:
                    transient += 1
                    log.info("probe_5xx_retry", hotel=hotel.id, status=response.status)
                    await self._backoff(self._backoff_seconds)
                    continue
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.HTTP,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error=f"http {response.status}",
                    http_status=response.status,
                    session_id=session.id,
                    duration_ms=duration_ms,
                    raw_html=response.text,
                )
            parsed = self._parser(response.text, currency, adults)
            if parsed.csrf_token and parsed.csrf_token != session.csrf_token:
                session.csrf_token = parsed.csrf_token
            if parsed.outcome == PageOutcome.EMPTY and self._fallback is not None:
                log.info("probe_empty_page_fallback", hotel=hotel.id, checkin=str(checkin))
                return await self._fallback.probe(hotel, checkin, nights, adults)
            return probe_result_from_page(
                parsed,
                method=ProbeMethod.HTTP,
                checkin=checkin,
                nights=nights,
                adults=adults,
                raw_html=response.text,
                http_status=response.status,
                session_id=session.id,
                duration_ms=duration_ms,
            )

    async def _fallback_or_blocked(
        self,
        hotel: HotelRef,
        checkin: date,
        nights: int,
        adults: int,
        http_status: int | None,
        session_id: str | None,
    ) -> ProbeResult:
        if self._fallback is None:
            return failed_result(
                ProbeStatus.BLOCKED,
                method=ProbeMethod.HTTP,
                checkin=checkin,
                nights=nights,
                adults=adults,
                error="blocked after retries",
                http_status=http_status,
                session_id=session_id,
            )
        return await self._fallback.probe(hotel, checkin, nights, adults)
