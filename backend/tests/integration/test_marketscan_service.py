"""Quét danh sách khu vực (thị trường toàn thành phố) với nguồn trang giả trả trang Booking thật.

Trang của các lát khám phá dựng từ trang thật bằng cách đổi slug/id trong kho Apollo (khách sạn
khác), bớt thẻ và đặt tổng số kênh báo.
"""

import functools
import gzip
import json
import re
import zlib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.base import ListingBlocked
from app.db.models import Hotel, Listing, Tenant
from app.marketscan import jobs
from app.marketscan.jobs import scan_market_list
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan
from app.marketscan.service import AreaTarget, MarketListService
from app.scheduler.channel_pause import MemoryChannelPauses

NOW = datetime(2026, 10, 2, 20, 5, tzinfo=UTC)  # 03:05 giờ Việt Nam ngày 03/10
NIGHT = date(2026, 10, 9)
_STORE = re.compile(r"(<script[^>]*data-capla-store-data=\"apollo\"[^>]*>)(.*?)(</script>)", re.S)


@pytest.fixture(scope="module")
def page1() -> str:
    path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "searchresults_hcmc_2026-10-09.html.gz"
    )
    return gzip.decompress(path.read_bytes()).decode("utf-8")


def variant(
    html: str,
    *,
    suffix: str = "",
    limit: int | None = None,
    checkin: date | None = None,
    total: int | None = None,
) -> str:
    """Trang khác dựng từ trang thật: đổi slug/id (khách sạn khác), bớt thẻ, đổi ngày hiển thị,
    tổng số kênh báo (facet giữ nguyên của trang thật)."""
    m = _STORE.search(html)
    assert m is not None
    store = json.loads(m.group(2))
    queries = store["ROOT_QUERY"]["searchQueries"]
    entry = next(v for k, v in queries.items() if k.startswith("search("))
    results = entry["results"][:limit] if limit is not None else entry["results"]
    for r in results:
        b = r["basicPropertyData"]
        if suffix:
            b["pageName"] = f"{b['pageName']}-{suffix}"
            b["id"] = int(f"{b['id']}9{zlib.crc32(suffix.encode()) % 100_000}")
    entry["results"] = results
    if checkin is not None:
        entry["searchMeta"]["dates"]["checkin"] = checkin.isoformat()
    if total is not None:
        entry["pagination"]["nbResultsTotal"] = total
    return m.group(1) + json.dumps(store) + m.group(3)  # chỉ kho Apollo, không thẻ HTML


Key = tuple[date, str, str]  # (đêm, nflt, order)


class FakeSource:
    """Trả trang theo (đêm, nflt, order); giá trị là Exception thì ném. Lát chưa khai báo: gọi
    `slice_page(đêm, số thứ tự lát)` nếu có."""

    def __init__(
        self,
        pages: dict[Key, str | Exception | list[str | Exception]],
        slice_page: Callable[[date, int], str | Exception] | None = None,
    ):
        self.pages = pages
        self.slice_page = slice_page
        self.urls: list[str] = []

    async def search_page(self, url: str) -> str:
        self.urls.append(url)
        q = parse_qs(urlparse(url).query)
        assert q["offset"] == ["0"]
        night = date.fromisoformat(q["checkin"][0])
        key = (night, q.get("nflt", [""])[0], q.get("order", [""])[0])
        value: str | Exception | list[str | Exception]
        if key in self.pages:
            value = self.pages[key]
        elif self.slice_page is not None:
            value = self.slice_page(night, len(self.urls))
        else:
            value = "<html></html>"
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if isinstance(value, Exception):
            raise value
        return value


def slices_of(page1: str, size: int = 10) -> Callable[[date, int], str]:
    """Mỗi lát khám phá: `size` khách sạn chưa thấy, lát liệt kê hết (tổng = số thẻ)."""
    return lambda night, n: variant(page1, suffix=f"s{n}", limit=size, total=size, checkin=night)


async def _no_sleep(_: float) -> None:
    return None


async def _area(db: AsyncSession, **kw: Any) -> MarketArea:
    t = Tenant(
        name="Rex",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(t)
    await db.flush()
    area = MarketArea(
        tenant_id=t.id,
        channel="booking",
        name="Ho Chi Minh City",
        dest_id="-3730078",
        dest_type="city",
        country_code="vn",
        list_nights=kw.pop("list_nights", 14),
        detail_horizon_days=30,
        detail_max_hotels=300,
        max_pages=kw.pop("max_pages", 60),
        active=True,
        list_requested_at=NOW - timedelta(minutes=5),
    )
    db.add(area)
    await db.commit()
    return area


def _target(area: MarketArea, max_requests: int | None = None) -> AreaTarget:
    return AreaTarget(
        area_id=area.id,
        channel="booking",
        dest_id=area.dest_id,
        dest_type=area.dest_type,
        max_requests=max_requests or area.max_pages,
        round_started=NOW - timedelta(minutes=5),
    )


def _svc(db: AsyncSession, source: FakeSource) -> MarketListService:
    sf = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return MarketListService(sf, source, FixedClock(NOW), backoff=_no_sleep)


async def _count(db: AsyncSession, model: Any) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


async def test_base_request_records_found_count_hotels_listings_prices(
    db: AsyncSession, page1: str
) -> None:
    area = await _area(db)
    # Khách sạn đã có trong hệ thống (tenant khác theo dõi): một trùng slug, một trùng id kênh.
    vela = Hotel(name="La Vela (đã theo dõi)", country_code="vn", lat=1.0, lng=2.0)
    ibis = Hotel(name="Ibis cũ", country_code="vn")
    db.add_all([vela, ibis])
    await db.flush()
    db.add_all(
        [
            Listing(
                hotel_id=vela.id,
                channel="booking",
                listing_key="vn/la-vela-saigon",
                url="https://www.booking.com/hotel/vn/la-vela-saigon.html",
                status="active",
            ),
            Listing(
                hotel_id=ibis.id,
                channel="booking",
                listing_key="vn/ibis-old-slug",
                external_id="2026902",
                url="https://www.booking.com/hotel/vn/ibis-old-slug.html",
                status="unverified",
            ),
        ]
    )
    await db.commit()
    source = FakeSource({(NIGHT, "", ""): page1}, slices_of(page1))

    result = await _svc(db, source).scan_night(_target(area), NIGHT)  # đêm thường: 1 request

    assert (result.status, result.pages, result.hotels_seen) == ("completed", 1, 25)
    assert result.properties_found == 3944 and result.priced == 25
    assert result.coverage == pytest.approx(25 / 3944)
    assert len(source.urls) == 1
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.status, scan.pages, scan.hotels_seen, scan.priced) == ("completed", 1, 25, 25)
    assert scan.finished_at is not None and scan.properties_found == 3944

    assert await _count(db, Hotel) == 25  # 23 mới + 2 đã có, không trùng
    assert await _count(db, MarketAreaHotel) == 25 and await _count(db, MarketListPrice) == 25
    await db.refresh(vela)
    await db.refresh(ibis)
    assert vela.name == "La Vela (đã theo dõi)" and (vela.lat, vela.lng) == (1.0, 2.0)
    assert (vela.review_count, vela.review_score, vela.star_rating) == (9467, Decimal("8.8"), 5)
    assert vela.district == "District 3" and vela.image_url
    assert ibis.review_count == 4669
    ibis_listing = (
        await db.execute(select(Listing).where(Listing.hotel_id == ibis.id))
    ).scalar_one()
    assert ibis_listing.status == "unverified"  # không đổi trạng thái listing đã có

    listing, hotel = (
        await db.execute(
            select(Listing, Hotel)
            .join(Hotel, Hotel.id == Listing.hotel_id)
            .where(Listing.listing_key == "vn/ancient-luxury-amp-spa")
        )
    ).one()
    assert (listing.status, listing.external_id, listing.channel) == (
        "active",
        "17311367",
        "booking",
    )
    assert listing.url == "https://www.booking.com/hotel/vn/ancient-luxury-amp-spa.html"
    assert (hotel.name, hotel.country_code, hotel.district) == (
        "Ancient Luxury Hotel & Spa",
        "vn",
        "District 1",
    )
    assert (hotel.lat, hotel.lng, hotel.star_rating) == (10.7704518, 106.6923346, Decimal("3"))
    price = (
        await db.execute(select(MarketListPrice).where(MarketListPrice.hotel_id == ibis.id))
    ).scalar_one()
    assert (price.rank, price.price, price.currency) == (7, Decimal("2092230"), "VND")
    ranks = dict(
        (await db.execute(select(MarketAreaHotel.hotel_id, MarketAreaHotel.best_rank))).all()
    )
    assert ranks[hotel.id] == 1 and max(ranks.values()) == 25


async def test_discovery_round_fetches_slices_until_request_budget(
    db: AsyncSession, page1: str
) -> None:
    area = await _area(db)
    source = FakeSource({(NIGHT, "", ""): page1}, slices_of(page1))
    result = await _svc(db, source).scan_night(_target(area, 5), NIGHT, discover=True)

    assert (result.status, result.pages, result.hotels_seen, result.priced) == (
        "completed",
        5,
        65,
        65,
    )
    queries = [parse_qs(urlparse(u).query) for u in source.urls]
    assert len(queries) == 5 and "nflt" not in queries[0] and "order" not in queries[0]
    slices = [(q.get("nflt", [""])[0], q.get("order", [""])[0]) for q in queries[1:]]
    assert all(n or o for n, o in slices) and len(set(slices)) == 4  # lát khác nhau
    assert await _count(db, MarketAreaHotel) == 65 and await _count(db, MarketListPrice) == 65
    ranks = [r for (r,) in (await db.execute(select(MarketAreaHotel.best_rank))).all()]
    # Hạng chỉ theo thứ tự mặc định của trang đầu; khách sạn từ lát khám phá không có hạng.
    assert sorted(r for r in ranks if r is not None) == list(range(1, 26))
    assert sum(1 for r in ranks if r is None) == 40
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.pages, scan.hotels_seen, scan.properties_found) == (5, 65, 3944)


async def test_discovery_stops_at_98_percent_of_found_count(db: AsyncSession, page1: str) -> None:
    area = await _area(db)
    source = FakeSource({(NIGHT, "", ""): variant(page1, total=30)}, slices_of(page1))
    result = await _svc(db, source).scan_night(_target(area, 60), NIGHT, discover=True)
    # Trang đầu 25/30; một lát nhỏ (≤ một trang) thêm 10 → 35 ≥ 98% của 30: dừng.
    assert (result.pages, result.hotels_seen, result.status) == (2, 35, "completed")
    assert result.coverage == 1.0


async def test_block_during_discovery_retries_once_then_stops_keeping_base(
    db: AsyncSession, page1: str
) -> None:
    area = await _area(db)
    source = FakeSource({(NIGHT, "", ""): page1}, lambda night, n: ListingBlocked("http 403"))
    result = await _svc(db, source).scan_night(_target(area), NIGHT, discover=True)
    assert (result.status, result.error) == ("blocked", "blocked")  # mã ngắn, chi tiết ở log
    assert len(source.urls) == 3  # trang đầu, một lát, thử lại lát đó một lần
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.status, scan.hotels_seen, scan.pages, scan.properties_found) == (
        "blocked",
        25,
        1,
        3944,
    )
    assert await _count(db, MarketListPrice) == 25


async def test_page_showing_other_dates_counts_as_blocked(db: AsyncSession, page1: str) -> None:
    area = await _area(db)
    other = NIGHT + timedelta(days=1)
    source = FakeSource({(other, "", ""): page1})  # trang hiện 2026-10-09 thay vì 10-10
    result = await _svc(db, source).scan_night(_target(area), other)
    assert result.status == "blocked" and len(source.urls) == 2
    assert result.properties_found is None
    assert await _count(db, Hotel) == 0


class _Collector:
    def __init__(self, source: FakeSource) -> None:
        self._source = source

    async def search_page(self, url: str) -> str:
        return await self._source.search_page(url)


class _Deps:
    def __init__(self, db: AsyncSession) -> None:
        self.session_factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
        self.clock = FixedClock(NOW)
        self.default_adults = 2


class _Queue:
    def __init__(self) -> None:
        self.market: list[tuple[int, str, str | None, int, int | None]] = []

    async def enqueue_market_list(
        self,
        area_id: int,
        channel: str,
        start: str | None = None,
        index: int = 0,
        round_ts: int | None = None,
    ) -> None:
        self.market.append((area_id, channel, start, index, round_ts))


def _ctx(
    db: AsyncSession, source: FakeSource, queue: _Queue, pauses: MemoryChannelPauses
) -> dict[str, Any]:
    return {
        "deps": _Deps(db),
        "collector": _Collector(source),
        "channel": "booking",
        "queue": queue,
        "pauses": pauses,
    }


async def test_job_chains_nights_skips_error_night_and_stops_when_blocked(
    db: AsyncSession, page1: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        jobs, "MarketListService", functools.partial(MarketListService, backoff=_no_sleep)
    )
    area = await _area(db, list_nights=4, max_pages=3)
    ts = int(area.list_requested_at.timestamp())  # type: ignore[union-attr]
    n1, n2, n3 = (NIGHT + timedelta(days=i) for i in (1, 2, 3))
    source = FakeSource(
        {
            (NIGHT, "", ""): variant(page1, limit=5, total=40),
            (n1, "", ""): [TimeoutError("proxy read timed out"), TimeoutError("again")],
            (n2, "", ""): ListingBlocked("http 429 https://www.booking.com/searchresults…"),
            (n3, "", ""): variant(page1, limit=5, checkin=n3, total=40),
        },
        slices_of(page1, size=5),
    )
    queue, pauses = _Queue(), MemoryChannelPauses(lambda: NOW)
    ctx = _ctx(db, source, queue, pauses)

    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 0, ts) == "completed"
    assert len(source.urls) == 1  # đêm thường: một request dù kênh báo 40 chỗ ở
    assert queue.market == [(area.id, "booking", NIGHT.isoformat(), 1, ts)]
    await db.refresh(area)
    assert (area.last_list_status, area.last_list_scan_at) == ("running", NOW)

    # Đêm lỗi mạng (đã thử lại một lần): bỏ qua, chuỗi đi tiếp; lỗi lưu dạng mã ngắn.
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 1, ts) == "error"
    assert queue.market[-1] == (area.id, "booking", NIGHT.isoformat(), 2, ts)
    await db.refresh(area)
    assert (area.last_list_status, area.last_list_error) == ("running", "error: timeout")

    # Bị chặn: dừng chuỗi, tạm dừng quét danh sách của kênh (probe không bị dừng).
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 2, ts) == "blocked"
    assert len(queue.market) == 2
    await db.refresh(area)
    assert (area.last_list_status, area.last_list_error) == ("blocked", "blocked")
    assert await pauses.is_paused("booking:market") and not await pauses.is_paused("booking")
    sent = len(source.urls)
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 3, ts) == "paused"
    assert len(source.urls) == sent

    # Hết tạm dừng: đêm cuối chuỗi cũng là đêm khám phá (vòng 4 đêm < đêm khám phá mặc định): thêm
    # lát tới hết ngân sách 3 request; xong thì "completed", không đẩy thêm.
    ctx["pauses"] = MemoryChannelPauses(lambda: NOW)
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 3, ts) == "completed"
    assert len(source.urls) == sent + 3
    scan = (
        await db.execute(select(MarketListScan).where(MarketListScan.stay_date == n3))
    ).scalar_one()
    assert (scan.pages, scan.hotels_seen) == (3, 15)
    await db.refresh(area)
    assert area.last_list_status == "completed" and len(queue.market) == 2
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 4, ts) == "done"

    # Vòng cũ (đã có vòng mới): job còn sót tự dừng, không gửi request.
    sent = len(source.urls)
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 1, ts - 3600) == "superseded"
    # Kênh đang tự ngắt vì tỉ lệ chặn probe: không gửi request nào.
    await ctx["pauses"].pause("booking", 30, "test")
    assert await scan_market_list(ctx, area.id, None, 0) == "paused"
    assert len(source.urls) == sent
