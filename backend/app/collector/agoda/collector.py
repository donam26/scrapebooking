"""Collector Agoda: API JSON qua curl_cffi (giả lập TLS Chrome), không cần trình duyệt hay cookie.

Probe = 1 GET `GetSecondaryData` (~1 MB JSON: bảng phòng, giá gồm thuế, tồn phòng, tín hiệu cầu).
Bảng phòng rỗng: thêm 1 POST `room-grid` để phân biệt hết phòng (`isSoldOut`) với không rõ lý do.
Bị chặn: thu hồi session (proxy mới, cookie mới), thử lại 1 lần.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any, Protocol

from app.collector.agoda import urls
from app.collector.agoda.parser import PARSER_VERSION as PARSER_VERSION
from app.collector.agoda.parser import (
    AgodaPage,
    PayloadError,
    SuggestHit,
    explicit_not_found,
    parse_identity,
    parse_property_data,
    parse_room_grid_sold_out,
    parse_suggest,
    property_id_from_html,
)
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import FetchOutcome, FetchResponse
from app.collector.matching import match_score, search_names
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult, ScrapeSession, SessionManager
from app.domain.models import (
    CalendarResult,
    ListingCandidate,
    ListingIdentity,
    ListingQuery,
    ListingRef,
    PageOutcome,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
)
from app.logging import get_logger

log = get_logger(__name__)

# API này không có dropdown số phòng: tồn phòng đi qua badge_count (số chính xác từ API).
DROPDOWN_CAP = 99
SUGGEST_LIMIT = 3  # số ứng viên được tra thêm URL + toạ độ (1 request mỗi ứng viên)
_STATUS_BY_OUTCOME = {
    PageOutcome.ROOMS: ProbeStatus.OK,
    PageOutcome.SOLD_OUT: ProbeStatus.SOLD_OUT,
    PageOutcome.EMPTY: ProbeStatus.NO_ROOMS_1N,
}


class AgodaError(RuntimeError):
    """Lỗi mạng/HTTP không phải chặn (probe -> ERROR; verify/suggest -> ListingBlocked)."""


class HttpClient(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        session: ScrapeSession,
        payload: dict[str, Any] | None = None,
    ) -> FetchResponse: ...
    async def close(self, session_id: str) -> None: ...
    async def close_all(self) -> None: ...


class AgodaHttp:
    """Một AsyncSession curl_cffi (proxy + cookie jar riêng) cho mỗi ScrapeSession. Không đặt
    User-Agent: để curl_cffi dùng UA khớp dấu vân tay TLS Chrome mà nó giả lập."""

    def __init__(self, timeout_s: float = 40.0, impersonate: str = "chrome") -> None:
        self._timeout = timeout_s
        self._impersonate = impersonate
        self._clients: dict[str, Any] = {}

    def _client(self, session: ScrapeSession) -> Any:
        client = self._clients.get(session.id)
        if client is None:
            from curl_cffi.requests import AsyncSession

            client = AsyncSession(
                impersonate=self._impersonate,
                proxies={"http": session.proxy.url, "https": session.proxy.url},
                timeout=self._timeout,
            )
            self._clients[session.id] = client
        return client

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        session: ScrapeSession,
        payload: dict[str, Any] | None = None,
    ) -> FetchResponse:
        t0 = time.monotonic()
        r = await self._client(session).request(method, url, headers=headers, json=payload)
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


class HttpOnlyBootstrapper:
    """Agoda không đòi cookie/token: session chỉ là proxy mới + cookie jar mới của curl_cffi."""

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        return BootstrapResult(cookies={}, user_agent="curl_cffi/chrome", csrf_token=None, html="")


def _classify(response: FetchResponse, expect_json: bool) -> FetchOutcome:
    """API JSON trả 200 mà body không phải JSON: coi là trang chặn/thử thách."""
    if expect_json and response.status == 200:
        return FetchOutcome.OK if response.text.lstrip()[:1] in ("{", "[") else FetchOutcome.BLOCKED
    return response.outcome


def _api_headers(referer: str, currency: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": referer,
        "ag-language-locale": urls.LOCALE,
        "cr-currency-code": currency,  # thiếu header này Agoda trả USD dù URL có currencyCode=VND
        "x-requested-with": "XMLHttpRequest",
    }


_PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


class AgodaCollector:
    def __init__(
        self,
        deps: CollectorDeps,
        http: HttpClient | None = None,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        backoff_seconds: float = 3.0,
    ) -> None:
        self._deps = deps
        self._http: HttpClient = http or AgodaHttp()
        self._sessions = SessionManager(
            bootstrapper=HttpOnlyBootstrapper(),
            proxy_provider=deps.proxy_provider,
            max_age=deps.session_max_age,
            max_requests=deps.session_max_requests,
            clock=deps.clock,
            listener=deps.session_listener,
            on_retire=[self._on_session_retired],
        )
        self._backoff = backoff
        self._backoff_seconds = backoff_seconds
        self._ids: dict[str, str] = {}  # listing_key -> propertyId đọc từ HTML

    async def _on_session_retired(self, session: ScrapeSession, reason: str) -> None:
        """Session hết hạn/bị chặn: đóng AsyncSession curl_cffi của nó, bỏ mốc giãn cách."""
        await self._http.close(session.id)
        self._deps.limiter.forget(session.id)

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        payload: dict[str, Any] | None = None,
        expect_json: bool = True,
        gate: bool = False,
    ) -> tuple[FetchResponse, FetchOutcome, ScrapeSession]:
        """Một request (ngân sách kênh + giãn cách theo session). Bị chặn: thu hồi session, thử lại
        1 lần với session mới. Lỗi mạng/5xx: thử lại 1 lần. Hết lượt: trả kết quả cuối cùng."""
        blocked = transient = 0
        while True:
            session = await self._sessions.get(self._deps.country, urls.BASE)
            await self._deps.budget.acquire()
            await self._deps.limiter.wait(session.id)
            sent = headers | self._gate_headers(session) if gate else headers
            try:
                response = await self._http.request(method, url, sent, session, payload)
            except Exception as exc:  # noqa: BLE001
                if transient < 1:
                    transient += 1
                    log.info("agoda_transport_retry", error=type(exc).__name__)
                    await self._backoff(self._backoff_seconds)
                    continue
                raise AgodaError(f"transport: {type(exc).__name__}: {exc}") from exc
            self._sessions.mark_request(session)
            outcome = _classify(response, expect_json)
            if outcome == FetchOutcome.BLOCKED:
                log.warning("agoda_blocked", status=response.status, url=url[:120], attempt=blocked)
                await self._sessions.retire(session, reason="blocked")  # hook đóng client
                if blocked < 1:
                    blocked += 1
                    await self._backoff(self._backoff_seconds)
                    continue
            elif outcome == FetchOutcome.ERROR and response.status >= 500 and transient < 1:
                transient += 1
                log.info("agoda_5xx_retry", status=response.status)
                await self._backoff(self._backoff_seconds)
                continue
            return response, outcome, session

    def _gate_headers(self, session: ScrapeSession) -> dict[str, str]:
        """Header web Agoda gửi kèm room-grid; ag-user-id ổn định trong một session."""
        user_id = session.extra.setdefault("ag_user_id", str(uuid.uuid4()))
        now_ms = int(self._deps.clock.now().timestamp() * 1000)
        return {
            "Origin": urls.BASE,
            "ag-cid": "-1",
            "ag-initiator-api-key": self._deps.keys.agoda_initiator_api_key,
            "ag-initiator-version": self._deps.keys.agoda_initiator_version,
            "ag-request-attempt": "1",
            "ag-retry-attempt": "0",
            "ag-user-id": user_id,
            "x-gate-meta": urls.gate_meta(now_ms, user_id),
        }

    async def _property_id(self, listing: ListingRef) -> str | None:
        """propertyId của listing; URL chỉ có slug thì đọc từ HTML trang khách sạn (một lần, có
        cache). None: trang không tồn tại."""
        known = urls.property_id(listing) or self._ids.get(listing.listing_key)
        if known:
            return known
        response, outcome, session = await self._send(
            "GET", listing.url, _PAGE_HEADERS, expect_json=False
        )
        if outcome == FetchOutcome.BLOCKED:
            raise ListingBlocked("blocked")
        if outcome == FetchOutcome.NOT_FOUND:
            return None
        if outcome != FetchOutcome.OK:
            raise AgodaError(f"http {response.status}")
        found = property_id_from_html(response.text)
        if not found:
            # Trang 200 không có propertyId: trang challenge/chặn mềm (URL sai thì Agoda trả 404).
            await self._sessions.retire(session, reason="blocked")
            raise ListingBlocked("no propertyId in page")
        self._ids[listing.listing_key] = found
        return found

    async def _identity(self, property_id: str, referer: str) -> ListingIdentity:
        """ListingBlocked: bị chặn, kể cả JSON 200 thiếu hotelInfo mà payload chưa đủ (chặn mềm).
        Trả identity không tên chỉ khi Agoda nói rõ id không tồn tại (explicit_not_found)."""
        response, outcome, session = await self._send(
            "GET", urls.secondary_data_url(property_id), _api_headers(referer, self._deps.currency)
        )
        if outcome == FetchOutcome.BLOCKED:
            raise ListingBlocked("blocked")
        if outcome != FetchOutcome.OK:
            raise AgodaError(f"http {response.status}")
        try:
            identity = parse_identity(response.text)
            if identity.name is None and not explicit_not_found(response.text):
                await self._sessions.retire(session, reason="blocked")
                raise ListingBlocked("incomplete payload: no hotelInfo")
        except PayloadError as exc:
            raise AgodaError(str(exc)) from exc
        return identity

    async def _sold_out(
        self, property_id: str, checkin: date, nights: int, adults: int, referer: str
    ) -> tuple[bool | None, FetchResponse | None]:
        payload = urls.room_grid_request(property_id, checkin, nights, adults, self._deps.currency)
        headers = _api_headers(referer, self._deps.currency)
        try:
            response, outcome, _ = await self._send(
                "POST", urls.BASE + urls.ROOM_GRID_PATH, headers, payload=payload, gate=True
            )
            if outcome != FetchOutcome.OK:
                return None, None
            return parse_room_grid_sold_out(response.text), response
        except (AgodaError, PayloadError) as exc:
            log.info("agoda_room_grid_failed", error=str(exc))
            return None, None

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        # Agoda không có lịch min-LOS công khai (GetCalendarExtrasAsync chỉ có ngày lễ/nhu cầu cao).
        return CalendarResult(ok=False, error="unsupported")

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        t0 = time.monotonic()
        currency = self._deps.currency

        def done(
            status: ProbeStatus,
            *,
            error: str | None = None,
            response: FetchResponse | None = None,
            session: ScrapeSession | None = None,
            page: AgodaPage | None = None,
            raw: str | None = None,
            extra_ms: int = 0,
        ) -> ProbeResult:
            # Thời gian mạng của request chính (không tính giãn cách của rate limiter).
            elapsed = response.elapsed_ms if response else int((time.monotonic() - t0) * 1000)
            return ProbeResult(
                status=status,
                method=ProbeMethod.API,
                checkin=checkin,
                checkout=checkin + timedelta(days=nights),
                nights=nights,
                adults=adults,
                offers=page.offers if page and status != ProbeStatus.ERROR else (),
                raw_html=raw if raw is not None else (response.text if response else None),
                http_status=response.status if response else None,
                session_id=session.id if session else None,
                duration_ms=elapsed + extra_ms,
                error=error,
                external_id=page.external_id if page else None,
                hotel_name=page.hotel_name if page else None,
                demand_signals=page.demand_signals if page else (),
            )

        try:
            property_id = await self._property_id(listing)
            if property_id is None:
                return done(ProbeStatus.ERROR, error="not_found")
            url = urls.secondary_data_url(property_id, checkin, nights, adults, currency)
            response, outcome, session = await self._send(
                "GET", url, _api_headers(listing.url, currency)
            )
        except ListingBlocked:
            return done(ProbeStatus.BLOCKED, error="blocked after retry")
        except AgodaError as exc:
            return done(ProbeStatus.ERROR, error=str(exc))
        if outcome == FetchOutcome.BLOCKED:
            error = "blocked after retry"
            return done(ProbeStatus.BLOCKED, error=error, response=response, session=session)
        if outcome == FetchOutcome.NOT_FOUND:
            return done(ProbeStatus.ERROR, error="not_found", response=response, session=session)
        if outcome != FetchOutcome.OK:
            error = f"http {response.status}"
            return done(ProbeStatus.ERROR, error=error, response=response, session=session)
        try:
            page = parse_property_data(response.text, adults)
        except PayloadError as exc:
            return done(ProbeStatus.ERROR, error=f"bad payload: {exc}", response=response)
        if page.hotel_name is None:
            if page.complete:
                # Agoda trả trọn dữ liệu cho id này mà không có khách sạn: không tồn tại thật.
                return done(
                    ProbeStatus.ERROR, error="not_found", response=response, session=session
                )
            # JSON 200 nhưng thiếu hotelInfo ở payload chưa đủ/có lỗi: chặn mềm → đổi session,
            # không bao giờ coi là listing hỏng.
            await self._sessions.retire(session, reason="blocked")
            return done(
                ProbeStatus.BLOCKED,
                error="incomplete payload: no hotelInfo",
                response=response,
                session=session,
            )
        if page.currency != currency:
            return done(
                ProbeStatus.ERROR,
                error=f"currency_mismatch:{page.currency}",
                response=response,
                session=session,
                page=page,
            )
        if page.checkin != checkin or page.nights != nights:
            return done(
                ProbeStatus.ERROR,
                error=f"agoda showed other dates: checkin {page.checkin} los {page.nights}",
                response=response,
                session=session,
                page=page,
            )
        if page.outcome == PageOutcome.EMPTY:
            sold_out, grid = await self._sold_out(property_id, checkin, nights, adults, listing.url)
            if sold_out and grid is not None:
                # Bằng chứng hết phòng nằm ở payload room-grid: lưu nó làm raw.
                return done(
                    ProbeStatus.SOLD_OUT,
                    response=response,
                    session=session,
                    page=page,
                    raw=grid.text,
                    extra_ms=grid.elapsed_ms,
                )
        return done(_STATUS_BY_OUTCOME[page.outcome], response=response, session=session, page=page)

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        """ListingNotFound: Agoda không có khách sạn ở URL/id này. ListingBlocked: bị chặn hoặc lỗi
        mạng/HTTP, thử lại sau."""
        try:
            property_id = await self._property_id(listing)
            if property_id is None:
                raise ListingNotFound(listing.url)
            identity = await self._identity(property_id, referer=listing.url)
        except AgodaError as exc:
            raise ListingBlocked(str(exc)) from exc
        if identity.name is None:
            raise ListingNotFound(listing.url)
        return identity

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        """API gợi ý của Agoda (không có toạ độ), thử lần lượt các biến thể tên; tra thêm URL chuẩn
        + toạ độ cho vài ứng viên đầu. Bị chặn/lỗi mạng: ListingBlocked."""
        referer = f"{urls.BASE}/{urls.LOCALE}/"
        headers = _api_headers(referer, self._deps.currency)
        country = query.country_code.lower()
        hits: list[SuggestHit] = []
        for variant in search_names(query.name):
            try:
                response, outcome, _ = await self._send("GET", urls.suggest_url(variant), headers)
            except AgodaError as exc:
                raise ListingBlocked(str(exc)) from exc
            if outcome != FetchOutcome.OK:
                raise ListingBlocked(f"suggest http {response.status}")
            try:
                found = parse_suggest(response.text)
            except PayloadError as exc:
                raise ListingBlocked(f"suggest {exc}") from exc
            hits = [h for h in found if h.country_code in (None, country)]
            if hits:
                break
        hits.sort(key=lambda h: match_score(query.name, h.name), reverse=True)
        candidates = []
        for hit in hits[:SUGGEST_LIMIT]:
            identity: ListingIdentity | None
            try:
                identity = await self._identity(hit.property_id, referer)
            except (ListingBlocked, AgodaError) as exc:
                log.info("agoda_suggest_identity_failed", id=hit.property_id, error=str(exc))
                identity = None
            if identity is not None and identity.name is None:
                continue  # id gợi ý nhưng không còn trang khách sạn
            candidates.append(_candidate(query, hit, identity))
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    async def close(self) -> None:
        await self._http.close_all()


def _candidate(
    query: ListingQuery, hit: SuggestHit, identity: ListingIdentity | None
) -> ListingCandidate:
    fallback = f"{urls.BASE}/{urls.LOCALE}/search?selectedproperty={hit.property_id}"
    listing = urls.parse_url(identity.url if identity and identity.url else fallback)
    assert listing is not None  # URL do chính module dựng, luôn là host agoda
    name = identity.name if identity and identity.name else hit.name
    lat = identity.lat if identity else None
    lng = identity.lng if identity else None
    query_ll = (query.lat, query.lng) if query.lat is not None and query.lng is not None else None
    cand_ll = (lat, lng) if lat is not None and lng is not None else None
    return ListingCandidate(
        channel="agoda",
        listing_key=listing.listing_key,
        url=listing.url,
        name=name,
        external_id=hit.property_id,
        address=identity.address if identity else None,
        lat=lat,
        lng=lng,
        country_code=(identity.country_code if identity else None) or hit.country_code,
        score=match_score(query.name, name, query_ll, cand_ll),
    )


def build(deps: CollectorDeps) -> AgodaCollector:
    return AgodaCollector(deps)
