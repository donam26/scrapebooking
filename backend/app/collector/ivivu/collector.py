"""Collector kênh ivivu.com.

- Giá: API JSON `HotelSearchReqContractAppV2`, mỗi lần gọi cần một token `X-ivv-key` dùng một lần.
  Token lấy từ trang ivivu mở sẵn trong Chromium (token_minter), request giá (~3 MB) đi bằng
  curl_cffi. Một session = một trình duyệt + một proxy, thay khi hết tuổi/số request hoặc bị chặn.
- Verify: trang khách sạn render sẵn (ng-state), không cần token.
- Gợi ý listing + tín hiệu cầu: `searchhotel`, `TopSale24hByHotel` (công khai, không token).
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.channels.registry import UnsupportedUrl
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import CurlFetcher, Fetcher, FetchOutcome
from app.collector.ivivu.api import (
    ORIGIN,
    PRICE_URL,
    price_headers,
    price_request,
    search_url,
    top_sale_url,
)
from app.collector.ivivu.parser import (
    PARSER_VERSION,
    bookings_month_signal,
    is_invalid_token,
    parse_hotel_page,
    parse_price_response,
    parse_search,
    top_sale_signal,
    trim_price_payload,
)
from app.collector.ivivu.token_minter import BrowserTokenMinter, TokenUnavailable
from app.collector.ivivu.urls import canonical_url, parse_url
from app.collector.matching import match_score, normalize_name, search_names
from app.collector.proxy import ProxyEndpoint
from app.collector.session import ScrapeSession
from app.domain.models import (
    CalendarResult,
    DemandSignal,
    ListingCandidate,
    ListingIdentity,
    ListingQuery,
    ListingRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RoomOffer,
)
from app.logging import get_logger

log = get_logger(__name__)

__all__ = ["DROPDOWN_CAP", "PARSER_VERSION", "IvivuCollector", "build"]

DROPDOWN_CAP = 99  # ivivu không có ô chọn số phòng (dropdown_max luôn None)
MINT_REQUESTS = 2  # mỗi token: challenge + get-session
PUBLIC_LIMITER_KEY = "ivivu:public"
SUGGEST_LIMIT = 5
STRONG_MATCH = 0.9  # suggest: đủ chắc thì không thử biến thể tên tiếp theo


class TokenMinter(Protocol):
    user_agent: str
    cookies: dict[str, str]

    async def mint(self) -> str | None: ...
    async def close(self) -> None: ...


MinterFactory = Callable[[ProxyEndpoint, str], Awaitable[TokenMinter]]
PublicGet = Callable[[str], Awaitable[tuple[int, str]]]  # url → (http status, body)


@dataclass
class _Session:
    scrape: ScrapeSession
    minter: TokenMinter


class IvivuCollector:
    def __init__(
        self,
        deps: CollectorDeps,
        *,
        fetcher: Fetcher | None = None,
        minter_factory: MinterFactory | None = None,
        public_get: PublicGet | None = None,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retries: int = 1,
        backoff_seconds: float = 3.0,
        demand_ttl: timedelta = timedelta(minutes=30),
    ) -> None:
        self._deps = deps
        self._fetcher: Fetcher = fetcher or CurlFetcher(timeout_s=60.0)
        self._minter_factory = minter_factory or self._launch_minter
        self._public_get = public_get or self._curl_get
        self._backoff = backoff
        self._retries = retries
        self._backoff_seconds = backoff_seconds
        self._demand_ttl = demand_ttl
        self._session: _Session | None = None
        self._hotel_ids: dict[str, int] = {}
        self._demand: dict[int, tuple[datetime, tuple[DemandSignal, ...]]] = {}
        self._client: Any = None  # curl_cffi AsyncSession cho request công khai

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return CalendarResult(ok=False, error="unsupported")  # ivivu không có lịch min-stay

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        t0 = time.monotonic()

        def failed(
            status: ProbeStatus,
            error: str,
            *,
            http_status: int | None = None,
            session_id: str | None = None,
            raw: str | None = None,
        ) -> ProbeResult:
            return _result(
                status,
                checkin,
                nights,
                adults,
                t0,
                error=error,
                http_status=http_status,
                session_id=session_id,
                raw=raw,
            )

        try:
            hotel_id = await self._hotel_id(listing)
        except ListingNotFound:
            return failed(ProbeStatus.ERROR, "not_found", http_status=404)
        except ListingBlocked as exc:
            return failed(ProbeStatus.BLOCKED, f"verify: {exc}")
        except Exception as exc:  # noqa: BLE001 - lỗi mạng khi đọc trang khách sạn
            return failed(ProbeStatus.ERROR, f"verify: {type(exc).__name__}: {exc}")
        payload = price_request(hotel_id, checkin, nights, adults)
        attempts = 0  # bị chặn / token hỏng: đổi session, thử lại `retries` lần
        transient = 0  # lỗi mạng / 5xx: thử lại trên cùng session
        while True:
            try:
                session = await self._get_session(listing.url)
            except Exception as exc:  # noqa: BLE001
                log.warning("ivivu_bootstrap_failed", error=f"{type(exc).__name__}: {exc}")
                if attempts < self._retries:
                    attempts += 1
                    await self._backoff(self._backoff_seconds * attempts)
                    continue
                status = (
                    ProbeStatus.BLOCKED if isinstance(exc, TokenUnavailable) else ProbeStatus.ERROR
                )
                return failed(status, f"bootstrap: {type(exc).__name__}: {exc}")
            sid = session.scrape.id
            await self._deps.limiter.wait(sid)
            for _ in range(MINT_REQUESTS):
                await self._deps.budget.acquire()
            token = await session.minter.mint()
            session.scrape.request_count += MINT_REQUESTS
            if token is None:
                await self._retire(session, "blocked")
                if attempts < self._retries:
                    attempts += 1
                    await self._backoff(self._backoff_seconds * attempts)
                    continue
                return failed(ProbeStatus.BLOCKED, "token_unavailable", session_id=sid)
            await self._deps.budget.acquire()
            try:
                response = await self._fetcher.post_json(
                    PRICE_URL, payload, price_headers(token), session.scrape
                )
            except Exception as exc:  # noqa: BLE001
                if transient < self._retries:
                    transient += 1
                    await self._backoff(self._backoff_seconds)
                    continue
                return failed(
                    ProbeStatus.ERROR, f"transport: {type(exc).__name__}: {exc}", session_id=sid
                )
            session.scrape.request_count += 1
            invalid_token = is_invalid_token(response.status, response.text)
            if invalid_token or response.outcome == FetchOutcome.BLOCKED:
                log.warning(
                    "ivivu_probe_blocked",
                    hotel=listing.id,
                    status=response.status,
                    invalid_token=invalid_token,
                    attempt=attempts,
                )
                await self._retire(session, "blocked")
                if attempts < self._retries:
                    attempts += 1
                    await self._backoff(self._backoff_seconds * attempts)
                    continue
                return failed(
                    ProbeStatus.BLOCKED,
                    "invalid_token" if invalid_token else f"http {response.status}",
                    http_status=response.status,
                    session_id=sid,
                    raw=response.text[:2000],
                )
            if response.status >= 500 and transient < self._retries:
                transient += 1
                await self._backoff(self._backoff_seconds)
                continue
            if response.status != 200:
                return failed(
                    ProbeStatus.ERROR,
                    f"http {response.status}",
                    http_status=response.status,
                    session_id=sid,
                    raw=response.text[:2000],
                )
            parsed = parse_price_response(response.text, adults, self._deps.currency)
            signals: tuple[DemandSignal, ...] = ()
            if parsed.status in (ProbeStatus.OK, ProbeStatus.SOLD_OUT):
                signals = await self._demand_signals(hotel_id, parsed.hotel_name)
            return _result(
                parsed.status,
                checkin,
                nights,
                adults,
                t0,
                error=parsed.error,
                http_status=response.status,
                session_id=sid,
                raw=trim_price_payload(response.text),
                offers=parsed.offers,
                external_id=str(hotel_id),
                hotel_name=parsed.hotel_name,
                signals=signals,
            )

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        status, text = await self._public(listing.url)
        if status == 404:
            raise ListingNotFound(listing.url)
        if status != 200:  # 403/429/503 của Cloudflare…: thử lại sau
            raise ListingBlocked(f"http {status}: {listing.url}")
        identity = parse_hotel_page(text, listing.url)
        if identity is None or not identity.external_id:
            raise ListingNotFound(listing.url)  # 200 nhưng không phải trang một khách sạn
        self._hotel_ids[listing.listing_key] = int(identity.external_id)
        return identity

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        """Thử lần lượt các biến thể tên, gộp kết quả, dừng khi đã có ứng viên khớp chắc.

        ivivu đặt tên tiếng Việt ("Khách sạn Rex Sài Gòn"); tên từ kênh khác thường tiếng Anh
        ("Rex Hotel Saigon") và chỉ khớp khách sạn khác cùng chữ "Saigon". Biến thể cuối là tên
        riêng không dấu, bỏ từ chung ("rex"): searchhotel trả khách sạn VN lên đầu."""
        latlng = (query.lat, query.lng) if query.lat is not None and query.lng is not None else None
        found: dict[str, ListingCandidate] = {}
        for keyword in _query_variants(query.name):
            for item in await self._search(keyword, query.country_code):
                cand = _candidate(item, query.name, latlng)
                if cand is not None:
                    found.setdefault(cand.listing_key, cand)
            if any(c.score >= STRONG_MATCH for c in found.values()):
                break
        return sorted(found.values(), key=lambda c: -c.score)[:SUGGEST_LIMIT]

    async def _search(self, keyword: str, country_code: str | None) -> list[dict[str, Any]]:
        status, text = await self._public(search_url(keyword))
        if status != 200:
            raise ListingBlocked(f"searchhotel http {status}")
        country = (country_code or "").lower()
        return [
            i
            for i in parse_search(text)
            if not country or str(i.get("countryCode") or "").lower() in ("", country)
        ]

    async def close(self) -> None:
        if self._session is not None:
            await self._retire(self._session, "closed")
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _hotel_id(self, listing: ListingRef) -> int:
        if listing.external_id and listing.external_id.isdigit():
            return int(listing.external_id)
        cached = self._hotel_ids.get(listing.listing_key)
        if cached is None:
            await self.verify(listing)
            cached = self._hotel_ids[listing.listing_key]
        return cached

    def _expired(self, s: _Session) -> bool:
        if s.scrape.retired or s.scrape.request_count >= self._deps.session_max_requests:
            return True
        return self._deps.clock.now() - s.scrape.created_at > self._deps.session_max_age

    async def _get_session(self, warmup_url: str) -> _Session:
        current = self._session
        if current is not None and not self._expired(current):
            return current
        if current is not None:
            await self._retire(current, "expired")
        proxy = self._deps.proxy_provider.new_endpoint(self._deps.country)
        await self._deps.budget.acquire()
        minter = await self._minter_factory(proxy, warmup_url)
        scrape = ScrapeSession(
            id=uuid.uuid4().hex[:16],
            proxy=proxy,
            cookies=minter.cookies,
            user_agent=minter.user_agent,
            csrf_token=None,
            created_at=self._deps.clock.now(),
        )
        self._session = _Session(scrape, minter)
        if self._deps.session_listener:
            await self._deps.session_listener.session_created(scrape)
        return self._session

    async def _retire(self, s: _Session, reason: str) -> None:
        if self._session is s:
            self._session = None
        if s.scrape.retired:
            return
        s.scrape.retired = True
        if reason == "blocked":
            s.scrape.block_count += 1
        try:
            await s.minter.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("ivivu_minter_close_failed", error=f"{type(exc).__name__}: {exc}")
        await self._fetcher.close(s.scrape.id)
        if self._deps.session_listener:
            await self._deps.session_listener.session_retired(s.scrape, reason)

    async def _launch_minter(self, proxy: ProxyEndpoint, warmup_url: str) -> TokenMinter:
        return await BrowserTokenMinter.launch(proxy, warmup_url, headless=self._deps.headless)

    async def _public(self, url: str) -> tuple[int, str]:
        await self._deps.budget.acquire()
        await self._deps.limiter.wait(PUBLIC_LIMITER_KEY)
        return await self._public_get(url)

    async def _curl_get(self, url: str) -> tuple[int, str]:
        if self._client is None:
            from curl_cffi.requests import AsyncSession

            proxy = self._deps.proxy_provider.new_endpoint(self._deps.country)
            self._client = AsyncSession(
                impersonate="chrome",
                proxies={"http": proxy.url, "https": proxy.url},
                timeout=30,
            )
        r = await self._client.get(
            url, headers={"Accept-Language": "vi-VN", "Referer": ORIGIN + "/"}
        )
        return int(r.status_code), str(r.text)

    async def _demand_signals(
        self, hotel_id: int, hotel_name: str | None
    ) -> tuple[DemandSignal, ...]:
        """Tín hiệu cả khách sạn (không theo đêm): gọi lại tối đa mỗi `demand_ttl`."""
        now = self._deps.clock.now()
        cached = self._demand.get(hotel_id)
        if cached is not None and now - cached[0] < self._demand_ttl:
            return cached[1]
        signals: list[DemandSignal] = []
        try:
            status, text = await self._public(top_sale_url(hotel_id))
            sold = top_sale_signal(text) if status == 200 else None
            if sold is not None:
                signals.append(sold)
            if hotel_name:
                status, text = await self._public(search_url(hotel_name))
                item = next((i for i in parse_search(text) if i.get("hotelId") == hotel_id), None)
                month = bookings_month_signal(item) if status == 200 and item else None
                if month is not None:
                    signals.append(month)
        except Exception as exc:  # noqa: BLE001 - tín hiệu phụ, không làm hỏng probe
            log.warning("ivivu_demand_failed", hotel_id=hotel_id, error=f"{type(exc).__name__}")
        self._demand[hotel_id] = (now, tuple(signals))
        return tuple(signals)


def _query_variants(name: str) -> list[str]:
    variants = search_names(name)
    core = normalize_name(name)
    if core and core not in (v.lower() for v in variants):
        variants.append(core)
    return variants


def _candidate(
    item: dict[str, Any], query_name: str, query_latlng: tuple[float, float] | None
) -> ListingCandidate | None:
    try:
        parsed = parse_url(canonical_url(str(item.get("hotelUrl") or "")))
    except UnsupportedUrl:
        return None
    if parsed is None:
        return None
    lat, lng = item.get("latitude"), item.get("longitude")
    latlng = (float(lat), float(lng)) if lat is not None and lng is not None else None
    name = str(item.get("hotelName") or "")
    return ListingCandidate(
        channel="ivivu",
        listing_key=parsed.listing_key,
        url=parsed.url,
        name=name,
        external_id=str(item["hotelId"]),
        address=str(item.get("address") or "").strip() or None,
        lat=latlng[0] if latlng else None,
        lng=latlng[1] if latlng else None,
        country_code=str(item.get("countryCode") or "vn").lower(),
        score=match_score(query_name, name, query_latlng, latlng),
    )


def _result(
    status: ProbeStatus,
    checkin: date,
    nights: int,
    adults: int,
    t0: float,
    *,
    error: str | None = None,
    http_status: int | None = None,
    session_id: str | None = None,
    raw: str | None = None,
    offers: tuple[RoomOffer, ...] = (),
    external_id: str | None = None,
    hotel_name: str | None = None,
    signals: tuple[DemandSignal, ...] = (),
) -> ProbeResult:
    return ProbeResult(
        status=status,
        method=ProbeMethod.API,
        checkin=checkin,
        checkout=checkin + timedelta(days=nights),
        nights=nights,
        adults=adults,
        offers=offers,
        raw_html=raw,
        http_status=http_status,
        session_id=session_id,
        duration_ms=int((time.monotonic() - t0) * 1000),
        error=error,
        external_id=external_id,
        hotel_name=hotel_name,
        demand_signals=signals,
    )


def build(deps: CollectorDeps) -> IvivuCollector:
    return IvivuCollector(deps)
