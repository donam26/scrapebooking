"""Collector kênh Mytour: gọi thẳng API JSON apis.tripi.vn bằng curl_cffi (không cần trình duyệt).

rooms/availability trả `completed: false` ở lần gọi đầu (máy chủ đang gom giá các nguồn), nên probe
gọi lại cùng body tới khi `completed: true`.
"""

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any, Literal, Protocol

from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import FetchOutcome, FetchResponse
from app.collector.matching import match_score
from app.collector.mytour.api import (
    API_BASE,
    AVAILABILITY_PATH,
    CODE_HOTEL_NOT_FOUND,
    CODE_OK,
    DETAIL_PATH,
    HOME_URL,
    SUGGEST_PATH,
    api_headers,
    availability_body,
)
from app.collector.mytour.parser import parse_availability, parse_identity, parse_suggestions
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult, ScrapeSession, SessionManager
from app.domain.models import (
    CalendarResult,
    ListingCandidate,
    ListingIdentity,
    ListingQuery,
    ListingRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
)
from app.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "curl_cffi/chrome"  # curl_cffi tự gửi UA khớp TLS fingerprint Chrome
HttpMethod = Literal["GET", "POST"]


class Transport(Protocol):
    async def send(
        self,
        session: ScrapeSession,
        method: HttpMethod,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> FetchResponse: ...

    async def close(self, session_id: str) -> None: ...
    async def close_all(self) -> None: ...


class CurlTransport:
    """Một AsyncSession curl_cffi (TLS Chrome) cho mỗi ScrapeSession, đi qua proxy của session."""

    def __init__(self, timeout_s: float = 30.0) -> None:
        self._timeout = timeout_s
        self._clients: dict[str, Any] = {}

    async def send(
        self,
        session: ScrapeSession,
        method: HttpMethod,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> FetchResponse:
        client = self._clients.get(session.id)
        if client is None:
            from curl_cffi.requests import AsyncSession

            client = AsyncSession(
                impersonate="chrome",
                proxies={"http": session.proxy.url, "https": session.proxy.url},
                timeout=self._timeout,
            )
            self._clients[session.id] = client
        t0 = time.monotonic()
        r = await client.request(method, url, headers=headers, json=json_body, params=params)
        return FetchResponse(
            status=r.status_code,
            text=r.text,
            url=str(r.url),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    async def close(self, session_id: str) -> None:
        client = self._clients.pop(session_id, None)
        if client is not None:
            await client.close()

    async def close_all(self) -> None:
        for sid in list(self._clients):
            await self.close(sid)


class ApiBootstrapper:
    """API không cần cookie/token từ trình duyệt: session chỉ là một IP proxy + deviceId."""

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        return BootstrapResult(cookies={}, user_agent=USER_AGENT, csrf_token=None, html="")


class MytourCollector:
    def __init__(
        self,
        deps: CollectorDeps,
        transport: Transport | None = None,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_polls: int = 10,
        http_retries: int = 1,
        backoff_seconds: float = 3.0,
    ) -> None:
        self._deps = deps
        self._sessions = SessionManager(
            bootstrapper=ApiBootstrapper(),
            proxy_provider=deps.proxy_provider,
            max_age=deps.session_max_age,
            max_requests=deps.session_max_requests,
            clock=deps.clock,
            listener=deps.session_listener,
        )
        self._transport = transport or CurlTransport()
        self._backoff = backoff
        self._max_polls = max_polls
        self._http_retries = http_retries
        self._backoff_seconds = backoff_seconds
        self._known_hotels: set[int] = set()

    async def _session(self) -> ScrapeSession:
        session = await self._sessions.get(self._deps.country, HOME_URL)
        if "device_id" not in session.extra:
            # Như web: `${Date.now()}-${Math.random()}`
            session.extra["device_id"] = f"{int(time.time() * 1000)}-{random.random()}"
        return session

    async def _send(
        self,
        session: ScrapeSession,
        method: HttpMethod,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> FetchResponse:
        await self._deps.budget.acquire()
        await self._deps.limiter.wait(session.id)
        now_s = self._deps.clock.now().timestamp()
        headers = api_headers(session.extra["device_id"], self._deps.currency, now_s)
        try:
            return await self._transport.send(
                session, method, API_BASE + path, headers, json_body=json_body, params=params
            )
        finally:
            self._sessions.mark_request(session)

    async def _retire_blocked(self, session: ScrapeSession) -> None:
        await self._sessions.retire(session, reason="blocked")
        await self._transport.close(session.id)

    async def _api(
        self, method: HttpMethod, path: str, json_body: dict[str, Any] | None = None, **params: str
    ) -> dict[str, Any]:
        """Gọi API cho verify/suggest: lỗi mạng/chặn → ListingBlocked (thử lại sau)."""
        session = await self._session()
        try:
            response = await self._send(session, method, path, json_body, params or None)
        except Exception as exc:  # noqa: BLE001
            raise ListingBlocked(f"transport: {type(exc).__name__}: {exc}") from exc
        if response.outcome == FetchOutcome.BLOCKED:
            await self._retire_blocked(session)
            raise ListingBlocked(f"http {response.status}: {path}")
        if response.outcome != FetchOutcome.OK:
            raise ListingBlocked(f"http {response.status}: {path}")
        try:
            payload: dict[str, Any] = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ListingBlocked(f"invalid json: {exc.msg}") from exc
        return payload

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return CalendarResult(ok=False, error="unsupported")

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        hotel_id = hotel_id_of(listing)
        body = availability_body(hotel_id, checkin, nights, adults)
        t0 = time.monotonic()
        polls = blocked = transient = 0
        session: ScrapeSession | None = None
        status: int | None = None

        def failed(probe_status: ProbeStatus, error: str, raw: str | None = None) -> ProbeResult:
            return ProbeResult(
                status=probe_status,
                method=ProbeMethod.API,
                checkin=checkin,
                checkout=checkin + timedelta(days=nights),
                nights=nights,
                adults=adults,
                offers=(),
                raw_html=raw,
                http_status=status,
                session_id=session.id if session else None,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
                external_id=str(hotel_id),
            )

        while True:
            session = await self._session()
            try:
                response = await self._send(session, "POST", AVAILABILITY_PATH, body)
            except Exception as exc:  # noqa: BLE001
                if transient < 1:
                    transient += 1
                    await self._backoff(self._backoff_seconds)
                    continue
                return failed(ProbeStatus.ERROR, f"transport: {type(exc).__name__}: {exc}")
            status = response.status
            if response.outcome == FetchOutcome.BLOCKED:
                log.warning("mytour_probe_blocked", hotel=listing.id, status=status)
                await self._retire_blocked(session)
                if blocked < self._http_retries:
                    blocked += 1
                    await self._backoff(self._backoff_seconds * blocked)
                    continue
                return failed(ProbeStatus.BLOCKED, "blocked after retries")
            if response.outcome != FetchOutcome.OK:
                if status >= 500 and transient < 1:
                    transient += 1
                    await self._backoff(self._backoff_seconds)
                    continue
                return failed(ProbeStatus.ERROR, f"http {status}", response.text)
            try:
                payload = json.loads(response.text)
            except json.JSONDecodeError:
                return failed(ProbeStatus.ERROR, "invalid json", response.text)
            if payload.get("code") != CODE_OK:
                code, message = payload.get("code"), payload.get("message")
                return failed(ProbeStatus.ERROR, f"api {code}: {message}", response.text)
            data = payload.get("data") or {}
            availability = parse_availability(
                data, adults, self._deps.currency, self._deps.clock.now()
            )
            if not availability.completed:
                polls += 1
                if polls >= self._max_polls:
                    if availability.offers:
                        # Đêm sát ngày (01–03/10, Park Hyatt) có thể không bao giờ "completed": dùng
                        # các nguồn đã trả giá thay vì bỏ cả đêm.
                        log.info("mytour_partial_availability", polls=polls)
                        break
                    error = f"incomplete after {polls} polls"
                    return failed(ProbeStatus.ERROR, error, response.text)
                continue
            break

        currencies = {r.currency for o in availability.offers for r in o.rates}
        if currencies - {self._deps.currency}:
            mismatch = sorted(currencies - {self._deps.currency})[0]
            return failed(ProbeStatus.ERROR, f"currency_mismatch:{mismatch}", response.text)
        probe_status = ProbeStatus.OK
        if not availability.offers:
            # Không còn giá nào: hết phòng trên Mytour, hoặc id không tồn tại.
            if not await self._hotel_exists(hotel_id):
                return failed(ProbeStatus.ERROR, "not_found", response.text)
            probe_status = ProbeStatus.SOLD_OUT
        return ProbeResult(
            status=probe_status,
            method=ProbeMethod.API,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=adults,
            offers=availability.offers,
            raw_html=response.text,
            http_status=status,
            session_id=session.id,
            duration_ms=int((time.monotonic() - t0) * 1000),
            external_id=str(hotel_id),
            demand_signals=availability.demand_signals,
        )

    async def _hotel_exists(self, hotel_id: int) -> bool:
        if hotel_id in self._known_hotels:
            return True
        try:
            payload = await self._api("POST", DETAIL_PATH, {"hotelId": hotel_id})
        except ListingBlocked:
            return True  # API giá đã báo "xong, 0 phòng"; chưa chắc id sai thì coi là hết phòng
        if payload.get("code") == CODE_HOTEL_NOT_FOUND:
            return False
        self._known_hotels.add(hotel_id)
        return True

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        hotel_id = hotel_id_of(listing)
        payload = await self._api("POST", DETAIL_PATH, {"hotelId": hotel_id})
        if payload.get("code") == CODE_HOTEL_NOT_FOUND:
            raise ListingNotFound(listing.url)
        if payload.get("code") != CODE_OK or not payload.get("data"):
            raise ListingBlocked(f"api {payload.get('code')}: {payload.get('message')}")
        self._known_hotels.add(hotel_id)
        return parse_identity(payload["data"])

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        payload = await self._api("GET", SUGGEST_PATH, term=query.name)
        if payload.get("code") != CODE_OK:
            raise ListingBlocked(f"api {payload.get('code')}: {payload.get('message')}")
        query_latlng = (
            (query.lat, query.lng) if query.lat is not None and query.lng is not None else None
        )
        out = []
        for s in parse_suggestions(payload.get("data") or {})[:5]:
            latlng = (s.lat, s.lng) if s.lat is not None and s.lng is not None else None
            out.append(
                ListingCandidate(
                    channel="mytour",
                    listing_key=str(s.hotel_id),
                    url=s.url,
                    name=s.name,
                    external_id=str(s.hotel_id),
                    address=s.address,
                    lat=s.lat,
                    lng=s.lng,
                    country_code=s.country_code,
                    score=match_score(query.name, s.name, query_latlng, latlng),
                )
            )
        return sorted(out, key=lambda c: -c.score)

    async def close(self) -> None:
        await self._transport.close_all()


def hotel_id_of(listing: ListingRef) -> int:
    return int(listing.external_id or listing.listing_key)


def build(deps: CollectorDeps) -> MytourCollector:
    return MytourCollector(deps)


# Hằng số worker đọc theo kênh.
from app.collector.mytour.parser import PARSER_VERSION as PARSER_VERSION  # noqa: E402

DROPDOWN_CAP = 99  # Mytour không có ô chọn số phòng; tồn phòng lấy từ badge_count (allotment)
