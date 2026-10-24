"""Quét một khu vực cho một đêm bằng GraphQL `FullSearch` của Booking (app/marketscan/graphql.py).

Mỗi đêm, trong trần `max_requests` request (đi qua session/proxy/ngân sách/giãn cách của kênh):
1. Thị trường: khu vực (+ bán kính), KHÔNG lọc phân khúc, `rowsPerPage = 1` → số còn phòng, % đã kín
   Booking tự tính (chỉ giữ khi truy vấn không có bộ lọc nào), facet (loại hình, hạng sao…). Khu vực
   không có phân khúc thì lấy luôn từ trang danh sách đầu, không tốn request riêng.
2. Danh sách: + phân khúc, 1 phòng 2 người lớn, 100 thẻ/request, theo thứ tự "phổ biến" (hạng
   hiển thị) tới hết; còn thiếu (thứ tự xáo giữa các request) thì lấp bằng trang sắp theo giá.
   Booking chỉ trả tối đa 1.000 kết quả/truy vấn. Ghi khách sạn, giá, hạng, "We have N left".
3. Thang: mỗi nấc N phòng (1 người lớn/phòng, sắp theo giá) → c(N) và theo hạng sao (facet). Đêm gần
   (`enumerate_ids`) lật đủ id → `rooms_min` từng khách sạn. c(N) = 0 thì dừng nấc cao hơn.
GraphQL lỗi schema (Booking đổi API) → dự phòng trang SSR đầu: số đếm, facet, ≤ 25 thẻ, không thang.
Bị chặn: thử lại một lần bằng session mới (như probe), rồi dừng hẳn và ghi trạng thái. Mỗi trang
được ghi ngay (dừng giữa chừng vẫn giữ phần đã có); hết trần request → "capped", giữ phần đã có.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.collector.base import ListingBlocked, ListingNotFound
from app.logging import get_logger
from app.marketscan.city import COVERAGE_TARGET
from app.marketscan.graphql import (
    MAX_ROWS,
    RESULT_CAP,
    SearchSchemaError,
    build_search_request,
    combine_nflt,
    parse_search_response,
    radius_nflt,
    search_location,
)
from app.marketscan.models import MarketListScan
from app.marketscan.parser import SearchCard, SearchPage, parse_search_page
from app.marketscan.upsert import record_page, record_rung
from app.marketscan.urls import SEARCH_URL, build_search_url

log = get_logger(__name__)


class SearchSource(Protocol):
    """Nguồn kết quả tìm kiếm của kênh (cài đặt trong `BookingCollector`). Ném ListingBlocked khi
    bị chặn."""

    async def search_graphql(self, payload: dict[str, Any], referer: str) -> str: ...

    async def search_page(self, url: str) -> str: ...


class SearchBlocked(RuntimeError):
    """Bị chặn sau khi đã thử lại. `code`: mã ngắn lưu DB/hiện cho tenant; chi tiết chỉ ở log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class WrongDates(ListingBlocked):
    """Kết quả mang ngày nhận phòng khác ngày yêu cầu (chặn mềm)."""


class _Capped(Exception):
    """Hết trần request của đêm."""


def error_code(exc: BaseException) -> str:
    """Mã lỗi ngắn, an toàn để hiện cho tenant (không lộ URL/proxy/traceback)."""
    if isinstance(exc, SearchSchemaError):
        return "error: schema"
    text = f"{type(exc).__name__} {exc}".lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "error: timeout"
    if isinstance(exc, OSError) or "curl" in text or "connection" in text:
        return "error: network"
    return "error: internal"


@dataclass(frozen=True)
class AreaTarget:
    area_id: int
    channel: str
    dest_id: str
    dest_type: str
    max_requests: int  # trần request của một đêm (gồm cả lần thử lại)
    round_started: datetime  # đầu lượt quét trong ngày (tính hạng tốt nhất của ngày)
    lat: float | None = None
    lng: float | None = None
    radius_m: int | None = None
    segment_nflt: str | None = None
    rungs: tuple[int, ...] = ()  # nấc thang (N phòng), tăng dần, ≤ 30

    @property
    def location(self) -> dict[str, Any]:
        return search_location(self.dest_type, self.dest_id, self.lat, self.lng)

    @property
    def area_nflt(self) -> str | None:
        """Bộ lọc của khu vực (bán kính) — truy vấn thị trường."""
        return radius_nflt(self.radius_m)

    @property
    def nflt(self) -> str | None:
        """Bộ lọc của phân khúc trong khu vực — danh sách và thang."""
        return combine_nflt(self.segment_nflt, self.area_nflt)


@dataclass
class NightResult:
    scan_id: int
    stay_date: date
    status: str = "running"
    pages: int = 0  # số request đã gửi cho đêm này
    hotels_seen: int = 0
    priced: int = 0
    properties_found: int | None = None
    error: str | None = None
    source: str | None = None
    autoextended: int | None = None
    low_availability: bool | None = None
    unavailability_pct: int | None = None
    market_available: int | None = None
    market_facets: dict[str, int] | None = None
    facets: dict[str, int] | None = None
    price_histogram: dict[str, Any] | None = None
    ladder: dict[str, Any] | None = None
    enumerated: bool = False

    @property
    def coverage(self) -> float | None:
        if not self.properties_found:
            return None
        return min(1.0, self.hotels_seen / self.properties_found)


def class_counts(facets: dict[str, int]) -> dict[str, int]:
    """{"3": 47, "4": 13…} từ facet `class=N` (khách sạn chưa xếp hạng không có trong facet)."""
    return {uid.split("=", 1)[1]: n for uid, n in facets.items() if uid.startswith("class=")}


class MarketListService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        source: SearchSource,
        clock: Clock,
        currency: str = "VND",
        adults: int = 2,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_seconds: float = 5.0,
    ) -> None:
        self._sf = session_factory
        self._source = source
        self._clock = clock
        self._currency = currency
        self._adults = adults
        self._backoff = backoff
        self._retry_seconds = retry_seconds

    # ---- request ----

    def _ssr_url(self, target: AreaTarget, night: date) -> str:
        if target.dest_type == "latlong":
            return SEARCH_URL
        return build_search_url(
            target.dest_id, target.dest_type, night, self._adults, self._currency, nflt=target.nflt
        )

    def _checked(self, page: SearchPage, night: date) -> SearchPage:
        if page.checkin is not None and page.checkin != night:
            raise WrongDates(f"search shows checkin {page.checkin}")
        return page

    async def _fetch(
        self, target: AreaTarget, result: NightResult, call: Callable[[], Awaitable[SearchPage]]
    ) -> SearchPage:
        """Một request (trong trần của đêm). Bị chặn, lỗi mạng/5xx hoặc lỗi GraphQL (có lúc chỉ tạm
        thời): thử lại một lần. Hết trần trước khi kịp thử lại thì ném lỗi gốc, không nuốt thành
        "capped"."""
        failure: BaseException | None = None
        for attempt in (0, 1):
            if result.pages >= target.max_requests:
                # Bị chặn mà hết trần trước khi kịp thử lại: chưa chắc là chặn → "capped", không
                # tạm dừng cả kênh; lỗi khác thì giữ nguyên lỗi.
                if failure is None or isinstance(failure, SearchBlocked):
                    raise _Capped()
                raise failure
            result.pages += 1
            try:
                return await call()
            except ListingNotFound as exc:
                raise SearchBlocked("blocked: not found", str(exc)) from exc
            except ListingBlocked as exc:
                code = "blocked: wrong dates" if isinstance(exc, WrongDates) else "blocked"
                failure = SearchBlocked(code, str(exc))
                if attempt:
                    raise failure from exc
                log.warning("market_list_blocked_retry", area_id=target.area_id, error=str(exc))
            except Exception as exc:  # noqa: BLE001 — mạng/5xx/lỗi GraphQL: thử lại một lần
                failure = exc
                if attempt:
                    raise
                log.warning("market_list_retry", area_id=target.area_id, error=repr(exc))
            await self._backoff(self._retry_seconds)
        raise AssertionError("unreachable")

    async def _gql(
        self,
        target: AreaTarget,
        night: date,
        result: NightResult,
        *,
        nflt: str | None,
        rooms: int = 1,
        adults: int | None = None,
        rows: int = MAX_ROWS,
        offset: int = 0,
        sorter: str | None = None,
    ) -> SearchPage:
        payload = build_search_request(
            target.location,
            night,
            adults=adults or self._adults,
            rooms=rooms,
            nflt=nflt,
            rows=rows,
            offset=offset,
            sorter=sorter,
        )
        referer = self._ssr_url(target, night)

        async def call() -> SearchPage:
            text = await self._source.search_graphql(payload, referer)
            return self._checked(parse_search_response(text, offset), night)

        return await self._fetch(target, result, call)

    # ---- một đêm ----

    async def scan_night(
        self, target: AreaTarget, night: date, enumerate_ids: bool = False
    ) -> NightResult:
        async with self._sf() as s:
            scan = MarketListScan(
                area_id=target.area_id,
                stay_date=night,
                scanned_at=self._clock.now(),
                status="running",
                pages=0,
                hotels_seen=0,
                priced=0,
                nflt=target.nflt,
            )
            s.add(scan)
            await s.commit()
            result = NightResult(scan.id, night)
        try:
            await self._scan(target, night, enumerate_ids, result)
            status = "completed"
        except _Capped:
            status = "capped"
        except SearchBlocked as exc:
            log.warning("market_list_blocked", area_id=target.area_id, error=str(exc))
            status, result.error = "blocked", exc.code
        except Exception as exc:  # noqa: BLE001
            log.exception("market_list_night_failed", area_id=target.area_id, night=str(night))
            status, result.error = "error", error_code(exc)
        result.status = status
        await self._save(result)
        log.info(
            "market_list_night_done",
            area_id=target.area_id,
            night=str(night),
            status=status,
            source=result.source,
            requests=result.pages,
            found=result.properties_found,
            seen=result.hotels_seen,
            rungs=len(result.ladder or {}),
            enumerated=result.enumerated,
        )
        return result

    async def _scan(
        self, target: AreaTarget, night: date, enumerate_ids: bool, result: NightResult
    ) -> None:
        """Thị trường → trang danh sách đầu → trang đầu của mọi nấc (thang đủ nấc sớm, hết trần
        giữa chừng vẫn có) → các trang danh sách còn lại → lật tiếp id từng nấc (đêm gần)."""
        try:
            if target.segment_nflt:
                market = await self._gql(target, night, result, nflt=target.area_nflt, rows=1)
                result.source = "graphql"
                self._market(target, market, result)
            first = await self._gql(target, night, result, nflt=target.nflt)
            result.source = "graphql"
        except SearchSchemaError as exc:
            if result.source is not None:
                raise  # lỗi sau khi GraphQL đã trả lời: không trộn hai nguồn trong một đêm
            log.error("market_graphql_schema_error", area_id=target.area_id, error=str(exc))
            await self._scan_ssr(target, night, result)
            return
        seen: set[str] = set()
        self._segment(target, first, result)
        await self._record(target, result, first.cards, seen, rank_from=0)
        await self._save(result)
        firsts = await self._ladder_counts(target, night, enumerate_ids, result)
        list_done = await self._list_rest(target, night, result, first, seen)
        if enumerate_ids:
            result.enumerated = await self._ladder_ids(target, night, result, firsts) and list_done

    def _market(self, target: AreaTarget, page: SearchPage, result: NightResult) -> None:
        result.market_available = page.total
        # % của Booking chia cho tổng khu vực không lọc: có bộ lọc (bán kính) thì sai nghĩa.
        result.unavailability_pct = page.unavailability_pct if target.area_nflt is None else None
        # Khu vực sắp kín: facet có thể đếm cả phần Booking nới thêm ngoài khu vực → không giữ.
        result.market_facets = (page.facets or None) if not page.autoextended else None

    def _segment(self, target: AreaTarget, page: SearchPage, result: NightResult) -> None:
        result.properties_found = page.total
        result.autoextended = page.autoextended
        result.low_availability = page.low_availability
        result.facets = page.facets or None
        result.price_histogram = page.histogram.to_json() if page.histogram else None
        if not target.segment_nflt:
            self._market(target, page, result)

    async def _list_rest(
        self,
        target: AreaTarget,
        night: date,
        result: NightResult,
        first: SearchPage,
        seen: set[str],
    ) -> bool:
        """Các trang danh sách sau trang đầu: thứ tự "phổ biến" tới hết; còn thiếu quá 2% (thứ tự
        xáo giữa các request) thì lấp theo giá — thiếu vài khách sạn (kênh đếm nhưng không trả)
        không đáng lật lại cả danh sách. Bước lật = số kết quả kênh thực trả; trang ngắn = hết.
        True khi danh sách đủ (≥ 98% số kênh báo và không vượt trần 1.000 kết quả của kênh)."""
        total = first.total or 0
        want = min(total, RESULT_CAP)
        for sorter in (None, "price"):
            if sorter is not None and len(seen) >= want * COVERAGE_TARGET:
                break
            offset = first.raw_count if sorter is None else 0
            # Chặn trên là trần 1.000 của kênh (không phải số trong khu vực): kết quả nới thêm có
            # thể xen giữa danh sách; trang ngắn = hết.
            while len(seen) < want and offset < RESULT_CAP:
                page = await self._gql(
                    target, night, result, nflt=target.nflt, offset=offset, sorter=sorter
                )
                await self._record(
                    target, result, page.cards, seen, rank_from=offset if sorter is None else None
                )
                if page.raw_count < MAX_ROWS:
                    break  # trang ngắn = hết danh sách (còn thiếu thì lấp theo giá ở trên)
                offset += page.raw_count
        return total <= RESULT_CAP and len(seen) >= want * COVERAGE_TARGET

    async def _ladder_counts(
        self, target: AreaTarget, night: date, enumerate_ids: bool, result: NightResult
    ) -> dict[int, tuple[SearchPage, set[str]]]:
        """Trang đầu của mọi nấc (N phòng, 1 người lớn/phòng, sắp theo giá): số đếm c(N) + theo
        hạng sao; đêm gần lấy luôn 100 id đầu. `ladder` chỉ được ghi khi đã đếm đủ mọi nấc (nấc trên
        một nấc 0 điền 0), nên không bao giờ có thang thiếu nấc cao."""
        ladder: dict[str, Any] = {}
        firsts: dict[int, tuple[SearchPage, set[str]]] = {}
        rungs = list(target.rungs)
        for i, n in enumerate(rungs):
            page = await self._gql(
                target,
                night,
                result,
                nflt=target.nflt,
                rooms=n,
                adults=n,
                rows=MAX_ROWS if enumerate_ids else 1,
                sorter="price",
            )
            ladder[str(n)] = {
                "available": page.total,
                "autoextended": page.autoextended,
                # Sắp kín (có phần nới thêm): facet hạng sao có thể đếm cả ngoài khu vực.
                "class": class_counts(page.facets) if not page.autoextended else {},
            }
            if enumerate_ids:
                await self._record_rung(target, result, page.cards, n)
                firsts[n] = (page, {c.slug for c in page.cards})
            if page.total == 0:
                for m in rungs[i + 1 :]:  # không ai bán được N phòng: nấc cao hơn cũng 0
                    ladder[str(m)] = {"available": 0, "autoextended": 0, "class": {}}
                break
        result.ladder = ladder
        await self._save(result)
        return firsts

    async def _ladder_ids(
        self,
        target: AreaTarget,
        night: date,
        result: NightResult,
        firsts: dict[int, tuple[SearchPage, set[str]]],
    ) -> bool:
        """Lật tiếp từng nấc tới đủ id → `rooms_min`. True khi mọi nấc đủ (≥ 98% số kênh báo);
        nấc vượt trần 1.000 của kênh thì dừng: khoảng phòng từng khách sạn sẽ sai."""
        complete = True
        for n, (first, seen) in firsts.items():
            total = first.total or 0
            if total > RESULT_CAP:
                return False
            offset = first.raw_count
            while len(seen) < total and offset < RESULT_CAP:
                page = await self._gql(
                    target,
                    night,
                    result,
                    nflt=target.nflt,
                    rooms=n,
                    adults=n,
                    offset=offset,
                    sorter="price",
                )
                fresh = [c for c in page.cards if c.slug not in seen]
                seen.update(c.slug for c in fresh)
                await self._record_rung(target, result, fresh, n)
                if page.raw_count < MAX_ROWS:
                    break  # trang ngắn = hết danh sách của nấc
                offset += page.raw_count
            complete = complete and len(seen) >= total * COVERAGE_TARGET
        return complete

    async def _scan_ssr(self, target: AreaTarget, night: date, result: NightResult) -> None:
        """Dự phòng khi GraphQL đổi schema: trang SSR đầu (≤ 25 thẻ), không thang."""
        if target.dest_type == "latlong":
            raise SearchSchemaError("graphql unavailable; latlong areas have no SSR fallback")
        url = self._ssr_url(target, night)

        async def call() -> SearchPage:
            return self._checked(parse_search_page(await self._source.search_page(url)), night)

        page = await self._fetch(target, result, call)
        if not page.cards and page.total is None:
            raise SearchBlocked("blocked: unexpected page", "no results and no total")
        result.source = "ssr"
        self._segment(target, page, result)
        await self._record(target, result, page.cards, set(), rank_from=0)

    # ---- ghi ----

    async def _record(
        self,
        target: AreaTarget,
        result: NightResult,
        cards: list[SearchCard],
        seen: set[str],
        rank_from: int | None,
    ) -> None:
        """Thẻ chưa thấy trong đêm: `rank_from` = offset của trang theo thứ tự "phổ biến" (hạng =
        offset + vị trí); None = trang lấp theo giá (không có hạng)."""
        ranked: list[tuple[int | None, SearchCard]] = []
        for i, card in enumerate(cards):
            if card.slug in seen:
                continue
            seen.add(card.slug)
            ranked.append((rank_from + i + 1 if rank_from is not None else None, card))
        if not ranked:
            return
        priced = [c for _, c in ranked if c.price is not None]
        other = {str(c.currency) for c in priced if c.currency != self._currency}
        if other:  # phiên không ở VND: giá bị bỏ (không quy đổi) — phải thấy trong log
            log.warning("market_currency_mismatch", area_id=target.area_id, found=sorted(other))
        async with self._sf() as s:
            await record_page(
                s,
                area_id=target.area_id,
                scan_id=result.scan_id,
                channel=target.channel,
                ranked=ranked,
                now=self._clock.now(),
                round_started=target.round_started,
                currency=self._currency,
            )
            await s.commit()
        result.hotels_seen += len(ranked)
        result.priced += sum(
            1 for _, c in ranked if c.price is not None and c.currency == self._currency
        )

    async def _record_rung(
        self, target: AreaTarget, result: NightResult, cards: list[SearchCard], rooms: int
    ) -> None:
        if not cards:
            return
        async with self._sf() as s:
            await record_rung(
                s,
                area_id=target.area_id,
                scan_id=result.scan_id,
                channel=target.channel,
                cards=cards,
                rooms=rooms,
                now=self._clock.now(),
                round_started=target.round_started,
            )
            await s.commit()

    async def _save(self, r: NightResult) -> None:
        done = r.status != "running"
        async with self._sf() as s:
            await s.execute(
                update(MarketListScan)
                .where(MarketListScan.id == r.scan_id)
                .values(
                    status=r.status,
                    pages=r.pages,
                    hotels_seen=r.hotels_seen,
                    priced=r.priced,
                    properties_found=r.properties_found,
                    error=r.error,
                    finished_at=self._clock.now() if done else None,
                    source=r.source,
                    autoextended=r.autoextended,
                    low_availability=r.low_availability,
                    unavailability_pct=r.unavailability_pct,
                    market_available=r.market_available,
                    market_facets=r.market_facets,
                    facets=r.facets,
                    price_histogram=r.price_histogram,
                    ladder=r.ladder,
                    enumerated=r.enumerated,
                )
            )
            await s.commit()
