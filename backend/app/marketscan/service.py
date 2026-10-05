"""Quét danh sách một khu vực cho một đêm.

- Mỗi đêm: một request (thứ tự mặc định) → `properties_found` (số chỗ ở còn phòng kênh báo — con số
  tin cậy) + giá trang đầu.
- Đêm khám phá (một lần mỗi ngày): thêm các "lát" bộ lọc × thứ tự (app/marketscan/slices.py) để
  mở rộng danh sách khách sạn của khu vực và lấy thêm giá đêm đó, tới khi thấy ≥ 98% số kênh báo
  hoặc hết ngân sách request (`max_requests`). Trang SSR bỏ qua `offset` nên không lật trang.

Request đi qua session/proxy/ngân sách/giãn cách sẵn có của kênh (`SearchPageSource`, cài đặt trong
`BookingCollector.search_page`). Bị chặn: thử lại một lần bằng session mới (như probe), rồi dừng hẳn
và ghi trạng thái, không gửi thêm. Mỗi trang được ghi ngay (dừng giữa chừng vẫn giữ phần đã có).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.collector.base import ListingBlocked, ListingNotFound
from app.logging import get_logger
from app.marketscan.models import MarketListScan
from app.marketscan.parser import SearchCard, SearchPage, parse_search_page
from app.marketscan.slices import Slice, SlicePlanner
from app.marketscan.upsert import record_page
from app.marketscan.urls import build_search_url

log = get_logger(__name__)


class SearchPageSource(Protocol):
    """Tải một trang kết quả tìm kiếm của kênh. Ném ListingBlocked khi bị chặn."""

    async def search_page(self, url: str) -> str: ...


class SearchBlocked(RuntimeError):
    """Bị chặn sau khi đã thử lại. `code`: mã ngắn lưu DB/hiện cho tenant; chi tiết chỉ ở log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class WrongDates(ListingBlocked):
    """Trang hiện ngày nhận phòng khác ngày yêu cầu (chặn mềm)."""


def error_code(exc: BaseException) -> str:
    """Mã lỗi ngắn, an toàn để hiện cho tenant (không lộ URL/proxy/traceback)."""
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
    max_requests: int  # ngân sách request của đêm khám phá (gồm request đầu)
    round_started: datetime  # đầu lượt quét trong ngày (tính hạng tốt nhất của ngày)


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

    @property
    def coverage(self) -> float | None:
        if not self.properties_found:
            return None
        return min(1.0, self.hotels_seen / self.properties_found)


class MarketListService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        source: SearchPageSource,
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

    async def _page(self, target: AreaTarget, night: date, s: Slice) -> SearchPage:
        """Trang đầu của một lát; bị chặn (kể cả trang không đúng ngày) thì thử lại một lần."""
        url = build_search_url(
            target.dest_id, target.dest_type, night, self._adults, self._currency, s.order, s.nflt
        )
        for attempt in (0, 1):
            try:
                page = parse_search_page(await self._source.search_page(url))
                if page.checkin is not None and page.checkin != night:
                    raise WrongDates(f"search page shows checkin {page.checkin}")
                return page
            except ListingNotFound as exc:
                raise SearchBlocked("blocked: not found", str(exc)) from exc
            except ListingBlocked as exc:
                if attempt:
                    code = "blocked: wrong dates" if isinstance(exc, WrongDates) else "blocked"
                    raise SearchBlocked(code, str(exc)) from exc
                log.warning("market_list_blocked_retry", url=url, error=str(exc))
            except Exception as exc:  # noqa: BLE001 — proxy/mạng: thử lại một lần
                if attempt:
                    raise
                log.warning("market_list_transport_retry", error=repr(exc))
            await self._backoff(self._retry_seconds)
        raise AssertionError("unreachable")

    async def scan_night(
        self, target: AreaTarget, night: date, discover: bool = False
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
            )
            s.add(scan)
            await s.commit()
            result = NightResult(scan.id, night)
        try:
            await self._scan(target, night, discover, result)
            status = "completed"
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
            discover=discover,
            requests=result.pages,
            seen=result.hotels_seen,
            found=result.properties_found,
        )
        return result

    async def _scan(
        self, target: AreaTarget, night: date, discover: bool, result: NightResult
    ) -> None:
        root = Slice()
        page = await self._page(target, night, root)
        result.pages = 1
        if not page.cards and page.total is None:
            raise SearchBlocked("blocked: unexpected page", "no results and no total")
        result.properties_found = page.total
        planner = SlicePlanner(page.total, page.per_page or len(page.cards) or 25)
        await self._record(target, result, planner.add_cards(page.cards), base=True)
        if not discover:
            return
        planner.observe(root, page)
        while result.pages < target.max_requests and not planner.done():
            s = planner.next()
            if s is None:
                break
            page = await self._page(target, night, s)
            result.pages += 1
            planner.observe(s, page)
            new = planner.add_cards(page.cards)
            log.info(
                "market_list_slice",
                area_id=target.area_id,
                nflt=s.nflt,
                order=s.order,
                total=page.total,
                cards=len(page.cards),
                new=len(new),
                seen=planner.seen,
            )
            await self._record(target, result, new, base=False)

    async def _record(
        self, target: AreaTarget, result: NightResult, cards: list[SearchCard], base: bool
    ) -> None:
        if cards:
            # Thứ tự thấy trong đêm: 1..N là trang đầu theo thứ tự mặc định của kênh.
            ranked = [(result.hotels_seen + i + 1, c) for i, c in enumerate(cards)]
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
                    area_rank=base,
                )
                await s.commit()
            result.hotels_seen += len(cards)
            result.priced += sum(
                1 for c in cards if c.price is not None and c.currency == self._currency
            )
        await self._save(result)

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
                )
            )
            await s.commit()
