"""Collector kênh Trip.com (vn.trip.com, POS Việt Nam, VND, không đăng nhập).

- probe: trình duyệt sống (browser.py) mở trang chi tiết theo ngày, bắt JSON
  `getHotelRoomListOversea`.
- verify: trang chi tiết SSR qua curl_cffi (không cần trình duyệt).
- suggest: API gợi ý `getHotelKeywords` qua curl_cffi (không cần cookie/token).
- calendar: Trip.com không có lịch min-LOS công khai → "unsupported".
"""

import json
import time
from datetime import date, timedelta
from typing import Any

from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import FetchOutcome, classify_response
from app.collector.matching import match_score, search_names
from app.collector.proxy import ProxyEndpoint
from app.collector.session import ScrapeSession, SessionManager
from app.collector.tripcom.browser import DetailLoad, TripcomBootstrapper
from app.collector.tripcom.parser import (
    HotelPage,
    build_payload,
    demand_signals,
    is_spider_blocked,
    parse_hotel_page,
    parse_room_list,
    parse_suggest,
)
from app.collector.tripcom.urls import build_detail_url, canonical_url, hotel_id
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

WARMUP_URL = "https://vn.trip.com/hotels/"
SUGGEST_URL = "https://vn.trip.com/restapi/soa2/34951/getHotelKeywords"


def api_headers(currency: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Origin": "https://vn.trip.com",
        "Referer": WARMUP_URL,
        "cookieorigin": "https://vn.trip.com",
        "currency": currency,
        "locale": "vi-VN",
        "x-ctx-country": "VN",
        "x-ctx-currency": currency,
        "x-ctx-locale": "vi-VN",
    }


def suggest_body(keyword: str, currency: str) -> dict[str, Any]:
    head = {
        "platform": "PC", "cver": "0", "cid": "", "bu": "IBU", "group": "trip", "aid": "",
        "sid": "", "ouid": "", "locale": "vi-VN", "region": "VN", "timezone": "7",
        "currency": currency, "pageId": "10320668150", "vid": "", "guid": "", "isSSR": False,
        "extension": [],
    }  # fmt: skip
    return {"queryInfo": {"keyword": keyword, "actionType": "destination"}, "head": head}


class TripcomCollector:
    def __init__(
        self,
        deps: CollectorDeps,
        browsers: TripcomBootstrapper | None = None,
        load_timeout_s: float = 90.0,
        block_retries: int = 1,
    ) -> None:
        self._deps = deps
        self._browsers = browsers or TripcomBootstrapper(headless=deps.headless)
        self._sessions = SessionManager(
            bootstrapper=self._browsers,
            proxy_provider=deps.proxy_provider,
            max_age=deps.session_max_age,
            max_requests=deps.session_max_requests,
            clock=deps.clock,
            listener=deps.session_listener,
            on_retire=[self._on_session_retired],
        )
        self._timeout_s = load_timeout_s
        self._block_retries = block_retries
        self._http: Any = None  # curl_cffi AsyncSession cho verify/suggest
        self._http_proxy: ProxyEndpoint | None = None

    async def _on_session_retired(self, session: ScrapeSession, reason: str) -> None:
        """Session hết hạn/bị chặn/đóng: đóng Chromium của nó, bỏ mốc giãn cách."""
        await self._browsers.close(session.proxy.id)
        self._deps.limiter.forget(session.id)

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return CalendarResult(ok=False, error="unsupported")

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        url = build_detail_url(listing, checkin, nights, adults, self._deps.currency)
        attempts = 0
        t0 = time.monotonic()
        while True:
            try:
                session = await self._sessions.get(self._deps.country, WARMUP_URL)
            except Exception as exc:  # noqa: BLE001 - mở Chromium/proxy hỏng: không nổ job
                log.warning("tripcom_bootstrap_failed", error=f"{type(exc).__name__}: {exc}")
                if attempts < self._block_retries:
                    attempts += 1
                    continue
                return self._failed(
                    ProbeStatus.BLOCKED,
                    checkin,
                    nights,
                    adults,
                    f"bootstrap: {type(exc).__name__}: {exc}",
                    None,
                    t0,
                )
            await self._browsers.close_others(session.proxy.id)
            browser = self._browsers.live.get(session.proxy.id)
            if browser is None:  # trình duyệt đã đóng (VD sau close()): bỏ session, mở mới
                await self._retire(session, "closed")
                continue
            await self._deps.budget.acquire()
            await self._deps.limiter.wait(session.id)
            t0 = time.monotonic()
            try:
                load = await browser.load_detail(url, self._timeout_s)
            except Exception as exc:  # noqa: BLE001
                await self._retire(session, "error")
                return self._failed(
                    ProbeStatus.ERROR,
                    checkin,
                    nights,
                    adults,
                    f"transport: {type(exc).__name__}: {exc}",
                    session,
                    t0,
                )
            self._sessions.mark_request(session)
            reason = self._block_reason(load)
            if reason is not None:
                log.warning(
                    "tripcom_probe_blocked", hotel=listing.id, checkin=str(checkin), reason=reason
                )
                await self._retire(session, "blocked")
                if attempts < self._block_retries:
                    attempts += 1
                    continue
                return self._failed(
                    ProbeStatus.BLOCKED,
                    checkin,
                    nights,
                    adults,
                    f"blocked: {reason}",
                    session,
                    t0,
                    load,
                )
            return self._result(listing, load, checkin, nights, adults, session, t0)

    @staticmethod
    def _block_reason(load: DetailLoad) -> str | None:
        """Trang rời trang chi tiết: "signin" (nghi bot) hoặc chuyển hướng khác (trang chủ…).
        Trip.com không trả 404 cho id sai mà chuyển hướng y như khi chặn mềm, không phân biệt
        được → coi là chặn (đổi session), không bao giờ là "không tồn tại". Hoặc API báo spider."""
        if load.left == "signin":
            return "signin"
        if load.left is not None:
            return f"redirected to {load.final_url}"
        if load.room_list is None:
            return None
        try:
            return "spider" if is_spider_blocked(json.loads(load.room_list)) else None
        except json.JSONDecodeError:
            return None

    def _result(
        self,
        listing: ListingRef,
        load: DetailLoad,
        checkin: date,
        nights: int,
        adults: int,
        session: ScrapeSession,
        t0: float,
    ) -> ProbeResult:
        if load.room_list is None:
            error = "timeout: room list not loaded"
            return self._failed(ProbeStatus.ERROR, checkin, nights, adults, error, session, t0)
        try:
            payload = json.loads(load.room_list)
        except json.JSONDecodeError as exc:
            return self._failed(
                ProbeStatus.ERROR, checkin, nights, adults, f"api: {exc.msg}", session, t0, load
            )
        page = parse_hotel_page(load.html) if load.html else HotelPage(hotel_id=None, name=None)
        parsed = parse_room_list(
            payload, currency=self._deps.currency, adults=adults, nights=nights, checkin=checkin
        )
        return ProbeResult(
            status=parsed.status,
            method=ProbeMethod.BROWSER,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=adults,
            offers=parsed.offers,
            raw_html=build_payload(page, load.room_list),
            http_status=load.http_status,
            session_id=session.id,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=parsed.error,
            external_id=page.hotel_id or hotel_id(listing),
            hotel_name=page.name,
            demand_signals=demand_signals(page),
        )

    @staticmethod
    def _failed(
        status: ProbeStatus,
        checkin: date,
        nights: int,
        adults: int,
        error: str,
        session: ScrapeSession | None,
        t0: float,
        load: DetailLoad | None = None,
    ) -> ProbeResult:
        return ProbeResult(
            status=status,
            method=ProbeMethod.BROWSER,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=adults,
            offers=(),
            raw_html=load.room_list if load else None,
            http_status=load.http_status if load else None,
            session_id=session.id if session else None,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=error,
        )

    async def _retire(self, session: ScrapeSession, reason: str) -> None:
        await self._sessions.retire(session, reason=reason)  # hook đóng Chromium của session

    # ------------------------------------------------------------ verify / suggest (curl_cffi)

    async def _request(self, method: str, url: str, **kwargs: Any) -> tuple[int, str, str]:
        if self._http is None:
            from curl_cffi.requests import AsyncSession

            self._http_proxy = self._deps.proxy_provider.new_endpoint(self._deps.country)
            proxy_url = self._http_proxy.url
            self._http = AsyncSession(
                impersonate="chrome", proxies={"http": proxy_url, "https": proxy_url}, timeout=30
            )
        assert self._http_proxy is not None
        await self._deps.budget.acquire()
        await self._deps.limiter.wait(f"http:{self._http_proxy.id}")
        r = await self._http.request(method, url, **kwargs)
        return int(r.status_code), str(r.text), str(r.url)

    async def _drop_http(self) -> None:
        if self._http is not None:
            await self._http.close()
        self._http, self._http_proxy = None, None

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        url = canonical_url(hotel_id(listing))
        status, html, final_url = await self._request(
            "GET", url, headers={"Accept-Language": "vi-VN,vi;q=0.9"}
        )
        outcome = classify_response(status, html)
        if outcome == FetchOutcome.NOT_FOUND:
            raise ListingNotFound(url)
        if outcome != FetchOutcome.OK:
            await self._drop_http()
            raise ListingBlocked(f"http {status}: {url}")
        page = parse_hotel_page(html)
        if page.hotel_id is None and page.name is None:
            # 200 nhưng không có dữ liệu khách sạn (kể cả bị chuyển về trang chủ): Trip.com không
            # nói rõ "không tồn tại", chặn mềm cũng chuyển hướng y hệt → đổi proxy, thử lại sau.
            await self._drop_http()
            raise ListingBlocked(f"no hotel data: {url} -> {final_url}")
        return ListingIdentity(
            external_id=page.hotel_id,
            name=page.name,
            url=canonical_url(page.hotel_id or hotel_id(listing)),
            address=page.address,
            city=page.city,
            country_code=page.country_code,
            lat=page.lat,
            lng=page.lng,
            star_rating=page.star_rating,
        )

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        currency = self._deps.currency
        hits = []
        for variant in search_names(query.name):
            status, text, _ = await self._request(
                "POST",
                SUGGEST_URL,
                json=suggest_body(variant, currency),
                headers=api_headers(currency),
            )
            if status != 200:
                await self._drop_http()
                raise ListingBlocked(f"suggest http {status}")
            try:
                hits = parse_suggest(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ListingBlocked(f"suggest invalid json: {exc.msg}") from exc
            if hits:
                break
        query_latlng = (
            (query.lat, query.lng) if query.lat is not None and query.lng is not None else None
        )
        out = [
            ListingCandidate(
                channel="tripcom",
                listing_key=h.hotel_id,
                url=canonical_url(h.hotel_id),
                name=h.name,
                external_id=h.hotel_id,
                address=h.subtitle,
                lat=h.lat,
                lng=h.lng,
                country_code=h.country_code,
                score=match_score(
                    query.name,
                    h.name,
                    query_latlng,
                    (h.lat, h.lng) if h.lat is not None and h.lng is not None else None,
                ),
            )
            for h in hits
        ]
        return sorted(out, key=lambda c: -c.score)

    async def close(self) -> None:
        await self._browsers.close_all()
        await self._drop_http()


def build(deps: CollectorDeps) -> TripcomCollector:
    return TripcomCollector(deps)


# Hằng số worker đọc theo kênh.
from app.collector.tripcom.parser import PARSER_VERSION as PARSER_VERSION  # noqa: E402

DROPDOWN_CAP = 10  # ô chọn số phòng của Trip.com dừng ở 10 (ruleInfo.maxQuantity)
