"""Quét khu vực một đêm (GraphQL `FullSearch`) với một "thị trường giả" trả lời như Booking.

`World`: mỗi khách sạn có loại chỗ ở, hạng sao, giá, số phòng còn. Truy vấn lọc theo bộ lọc nflt
(`ht_id`), `nbRooms` (phòng còn ≥ N), phân trang `rowsPerPage/offset`, thứ tự phổ biến (theo id)
hoặc giá; trả số đếm, facet hạng sao/loại chỗ ở, % đã kín (chỉ khi không lọc). Dự phòng SSR dùng
trang thật đã rút gọn (TP.HCM, 09/10).
"""

import functools
import gzip
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.base import ListingBlocked
from app.config import get_settings
from app.db.models import Hotel, Listing, Tenant
from app.marketscan import jobs
from app.marketscan.jobs import scan_market_list
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan
from app.marketscan.service import AreaTarget, MarketListService
from app.scheduler.channel_pause import MemoryChannelPauses

NOW = datetime(2026, 10, 16, 20, 5, tzinfo=UTC)  # 03:05 giờ Việt Nam ngày 17/10
NIGHT = date(2026, 10, 17)
RUNGS = (2, 5, 10, 20, 30)


@dataclass(frozen=True)
class Stay:
    idx: int
    type_id: int  # 204 khách sạn, 201 căn hộ
    stars: int
    price: int
    rooms: int  # phòng còn đêm đó (0 = hết)
    autoextended: bool = False


def default_world(n: int = 260) -> list[Stay]:
    """Khách sạn i: căn hộ khi i % 4 == 3; phòng còn = i % 35 (0 = hết); giá giảm dần theo i."""
    return [
        Stay(i, 201 if i % 4 == 3 else 204, 2 + i % 4, 2_000_000 - i * 5_000, i % 35)
        for i in range(n)
    ]


def card(h: Stay) -> dict[str, Any]:
    return {
        "basicPropertyData": {
            "id": 900_000 + h.idx,
            "pageName": f"hotel-{h.idx}",
            "accommodationTypeId": h.type_id,
            "location": {
                "countryCode": "vn",
                "city": "Vung Tau",
                "address": f"{h.idx} Thuy Van",
                "latitude": 10.34 + h.idx / 10_000,
                "longitude": 107.09,
            },
            "reviews": {"reviewsCount": 1000 - h.idx, "totalScore": 8.0},
            "starRating": {"value": h.stars},
            "photos": {"main": {"highResJpegUrl": {"relativeUrl": f"/x/{h.idx}.jpg"}}},
        },
        "displayName": {"text": f"Hotel {h.idx}"},
        "location": {"displayLocation": "Vung Tau", "mainDistance": "1 km from centre"},
        "priceDisplayInfoIrene": {
            "displayPrice": {"amountPerStay": {"amountUnformatted": h.price, "currency": "VND"}},
            "excludedCharges": {
                "excludeChargesAggregated": {"amountPerStay": {"amountUnformatted": 0}}
            },
            "badges": [],
        },
        "blocks": [
            {
                "onlyXLeftMessage": {"translation": f"We have {h.rooms} left at this price"}
                if h.rooms <= 3
                else None
            }
        ],
        "soldOutInfo": {"isSoldOut": False},
        "persuasion": {"autoextended": h.autoextended, "preferred": False},
        "badges": [],
        "showAdLabel": False,
        "sponsoredListingData": None,
    }


class World:
    """Trả lời `search_graphql` như Booking; ghi lại các input đã nhận."""

    def __init__(self, stays: list[Stay], night: date = NIGHT) -> None:
        self.stays = stays
        self.night = night
        self.inputs: list[dict[str, Any]] = []
        self.urls: list[str] = []
        self.fail: list[BaseException | str] = []  # lỗi/thân trả lời ép cho các request kế tiếp
        self.ssr_html: str | None = None
        self.histogram: list[int] | None = None
        # Khách sạn Booking đếm nhưng không trả ở thứ tự "phổ biến" (xáo giữa các request).
        self.hidden_popular: set[int] = set()
        # Kết quả nới thêm xen giữa danh sách: một thẻ nới thêm sau mỗi N thẻ trong khu vực.
        self.interleave: int | None = None

    async def search_graphql(self, payload: dict[str, Any], referer: str) -> str:
        inp = payload["variables"]["input"]
        self.inputs.append(inp)
        if self.fail:
            forced = self.fail.pop(0)
            if isinstance(forced, BaseException):
                raise forced
            return forced
        nflt = (inp["filters"] or {}).get("selectedFilters") or ""
        types = {int(x.split("=")[1]) for x in nflt.split(";") if x.startswith("ht_id=")}
        rooms = inp["nbRooms"]
        inside = [h for h in self.stays if h.rooms >= rooms and not h.autoextended]
        extended = [h for h in self.stays if h.rooms >= rooms and h.autoextended]
        match = [h for h in inside if not types or h.type_id in types]
        ext = [h for h in extended if not types or h.type_id in types]
        if inp["sorters"]["selectedSorter"] == "price":
            inside_order = sorted(match, key=lambda h: h.price)
        else:
            inside_order = [h for h in match if h.idx not in self.hidden_popular]
        if self.interleave:
            listed, rest = [], list(ext)
            for i, h in enumerate(inside_order, 1):
                listed.append(h)
                if i % self.interleave == 0 and rest:
                    listed.append(rest.pop(0))
            listed += rest
        else:
            listed = inside_order + ext
        page = inp["pagination"]
        rows = listed[page["offset"] : page["offset"] + page["rowsPerPage"]]
        classes: dict[int, int] = {}
        for h in match:
            classes[h.stars] = classes.get(h.stars, 0) + 1
        kinds: dict[int, int] = {}
        for h in inside:
            kinds[h.type_id] = kinds.get(h.type_id, 0) + 1
        total = len(self.stays)
        filters = [
            {
                "field": "class",
                "options": [{"urlId": f"class={k}", "count": v} for k, v in classes.items()],
            },
            {
                "field": "ht_id",
                "options": [{"urlId": f"ht_id={k}", "count": v} for k, v in kinds.items()],
            },
            {"field": "popular", "options": [{"urlId": "class=9", "count": 1}]},
        ]
        if self.histogram is not None:
            filters.append(
                {
                    "field": "price",
                    "options": [],
                    "sliderOptions": {
                        "min": "100000",
                        "max": "2000000",
                        "histogram": self.histogram,
                    },
                }
            )
        body = {
            "data": {
                "searchQueries": {
                    "search": {
                        "results": [card(h) for h in rows],
                        "pagination": {
                            "nbResultsPerPage": page["rowsPerPage"],
                            "nbResultsTotal": len(match) + len(ext),
                        },
                        "searchMeta": {
                            "availabilityInfo": {
                                "hasLowAvailability": len(match) < 20,
                                "unavailabilityPercent": round(100 * (1 - len(match) / total)),
                                "totalAvailableNotAutoextended": len(match),
                                "totalAutoextendedAvailable": len(ext),
                            },
                            "dates": {"checkin": self.night.isoformat()},
                            "nbRooms": rooms,
                            "nbAdults": inp["nbAdults"],
                        },
                        "filters": filters,
                    }
                }
            }
        }
        return json.dumps(body)

    async def search_page(self, url: str) -> str:
        self.urls.append(url)
        assert self.ssr_html is not None
        return self.ssr_html


async def _no_sleep(_: float) -> None:
    return None


async def _area(db: AsyncSession, **kw: Any) -> MarketArea:
    t = Tenant(
        name="Bai Sau Hotel",
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
        name=kw.pop("name", "Vung Tau"),
        dest_id=kw.pop("dest_id", "-3733750"),
        dest_type=kw.pop("dest_type", "city"),
        country_code="vn",
        list_nights=kw.pop("list_nights", 14),
        detail_horizon_days=30,
        detail_max_hotels=0,
        max_pages=kw.pop("max_pages", 60),
        active=True,
        list_requested_at=NOW - timedelta(minutes=5),
        **kw,
    )
    db.add(area)
    await db.commit()
    return area


def _target(
    area: MarketArea, max_requests: int | None = None, rungs: tuple[int, ...] = RUNGS
) -> AreaTarget:
    return AreaTarget(
        area_id=area.id,
        channel="booking",
        dest_id=area.dest_id,
        dest_type=area.dest_type,
        max_requests=max_requests or area.max_pages,
        round_started=NOW - timedelta(minutes=5),
        lat=area.lat,
        lng=area.lng,
        radius_m=area.radius_m,
        segment_nflt=area.segment_nflt,
        rungs=rungs,
    )


def _svc(db: AsyncSession, source: World) -> MarketListService:
    sf = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return MarketListService(sf, source, FixedClock(NOW), backoff=_no_sleep)


async def _count(db: AsyncSession, model: Any) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


async def _rooms_by_slug(db: AsyncSession) -> dict[str, tuple[int | None, int | None, int | None]]:
    rows = await db.execute(
        select(
            Listing.listing_key,
            MarketListPrice.rooms_min,
            MarketListPrice.rank,
            MarketListPrice.only_left,
        ).join(MarketListPrice, MarketListPrice.hotel_id == Listing.hotel_id)
    )
    return {key: (rooms, rank, left) for key, rooms, rank, left in rows}


def _expected_rung(rooms: int) -> int:
    return max([1, *[n for n in RUNGS if n <= rooms]])


async def test_segment_night_lists_all_hotels_and_ladder_with_ranges(db: AsyncSession) -> None:
    area = await _area(db, segment_nflt="ht_id=204")
    world = World(default_world())
    # Khách sạn đã có trong hệ thống (tenant khác theo dõi): dùng lại, không tạo trùng.
    known = Hotel(name="Hotel 1 (đã theo dõi)", country_code="vn")
    db.add(known)
    await db.flush()
    db.add(
        Listing(
            hotel_id=known.id,
            channel="booking",
            listing_key="vn/hotel-1",
            url="https://www.booking.com/hotel/vn/hotel-1.html",
            status="active",
        )
    )
    await db.commit()

    result = await _svc(db, world).scan_night(_target(area), NIGHT, enumerate_ids=True)

    hotels = [h for h in world.stays if h.type_id == 204 and h.rooms >= 1]
    c = {n: sum(1 for h in hotels if h.rooms >= n) for n in (1, *RUNGS)}
    assert c == {1: 189, 2: 183, 5: 165, 10: 135, 20: 79, 30: 27}
    # thị trường 1 + danh sách 2 trang phổ biến + thang 2+2+2+1+1 (lật đủ id ở mọi nấc)
    assert (result.status, result.source, result.pages) == ("completed", "graphql", 11)
    market, first = world.inputs[:2]
    assert (market["filters"], market["pagination"]["rowsPerPage"]) == ({}, 1)
    assert first["filters"] == {"selectedFilters": "ht_id=204"}
    # Trang đầu của mọi nấc ngay sau trang danh sách đầu (thang đủ nấc sớm), rồi mới lật tiếp.
    assert [i["nbRooms"] for i in world.inputs[2:7]] == list(RUNGS)
    second = world.inputs[7]
    assert (second["nbRooms"], second["pagination"]["offset"]) == (1, 100)
    assert (first["sorters"]["selectedSorter"], second["sorters"]["selectedSorter"]) == (None, None)
    rung10 = next(i for i in world.inputs if i["nbRooms"] == 10)
    assert (rung10["nbAdults"], rung10["sorters"]["selectedSorter"]) == (10, "price")
    assert rung10["pagination"]["rowsPerPage"] == 100

    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.properties_found, scan.hotels_seen, scan.priced, scan.pages) == (189, 189, 189, 11)
    assert (scan.market_available, scan.unavailability_pct) == (252, 3)  # 252/260 còn phòng
    assert scan.market_facets is not None and scan.market_facets["ht_id=201"] == 63
    assert scan.facets is not None and "class=9" not in scan.facets  # bỏ nhóm "popular"
    assert scan.ladder == {
        str(n): {
            "available": c[n],
            "autoextended": 0,
            "class": {
                str(k): sum(1 for h in hotels if h.rooms >= n and h.stars == k)
                for k in (2, 3, 4, 5)
                if any(h.rooms >= n and h.stars == k for h in hotels)
            },
        }
        for n in RUNGS
    }
    assert scan.enumerated is True and scan.source == "graphql" and scan.status == "completed"
    assert scan.nflt == "ht_id=204"

    rooms = await _rooms_by_slug(db)
    assert len(rooms) == 189 and await _count(db, MarketAreaHotel) == 189
    for h in hotels:
        rung, rank, left = rooms[f"vn/hotel-{h.idx}"]
        assert rung == _expected_rung(h.rooms)
        assert left == (h.rooms if h.rooms <= 3 else None)
    assert rooms["vn/hotel-1"][1] == 1  # hạng 1: đầu trang theo thứ tự phổ biến
    assert sorted(r for _, r, _ in rooms.values()) == list(range(1, 190))
    assert await _count(db, Hotel) == 189  # 188 mới + 1 đã có
    await db.refresh(known)
    assert known.name == "Hotel 1 (đã theo dõi)" and known.star_rating == 3


async def test_far_night_counts_only_and_stops_at_empty_rung(db: AsyncSession) -> None:
    area = await _area(db)
    world = World([Stay(i, 204, 3, 900_000 + i, 1 + i % 12) for i in range(40)])
    world.histogram = [0, 6, 100] + [0] * 47

    result = await _svc(db, world).scan_night(_target(area), NIGHT, enumerate_ids=False)

    # Không có phân khúc: thị trường lấy từ trang danh sách đầu. Thang chỉ đếm (rows = 1);
    # không ai còn ≥ 20 phòng → dừng, không hỏi nấc 30.
    assert (result.status, result.pages) == ("completed", 1 + 4)
    assert [i["nbRooms"] for i in world.inputs] == [1, 2, 5, 10, 20]
    assert all(i["pagination"]["rowsPerPage"] == 1 for i in world.inputs[1:])
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.properties_found, scan.market_available, scan.unavailability_pct) == (40, 40, 0)
    # Nấc trên nấc 0 được điền 0 (giao diện phân biệt "0" với "chưa quét").
    assert scan.ladder is not None and set(scan.ladder) == {"2", "5", "10", "20", "30"}
    assert scan.ladder["20"]["available"] == scan.ladder["30"]["available"] == 0
    assert scan.enumerated is False
    assert scan.price_histogram == {"min": 100000, "max": 2000000, "bars": [0, 6, 100] + [0] * 47}
    rooms = await _rooms_by_slug(db)
    assert {r for r, _, _ in rooms.values()} == {1}  # đêm xa: chỉ biết "≥ 1" từ danh sách


async def test_radius_area_filters_market_and_drops_booking_percentage(db: AsyncSession) -> None:
    area = await _area(
        db,
        name="3 km quanh khách sạn",
        dest_type="latlong",
        dest_id="10.34000,107.09000",
        lat=10.34,
        lng=107.09,
        radius_m=3000,
        segment_nflt="ht_id=204",
    )
    world = World(default_world(30))
    result = await _svc(db, world).scan_night(_target(area, rungs=(2,)), NIGHT)
    assert result.status == "completed"
    market, listing = world.inputs[0], world.inputs[1]
    assert market["location"] == {"destType": "LATLONG", "latitude": 10.34, "longitude": 107.09}
    assert market["filters"] == {"selectedFilters": "distance=3000"}
    assert listing["filters"] == {"selectedFilters": "ht_id=204;distance=3000"}
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert scan.unavailability_pct is None  # % của Booking có bộ lọc bán kính: sai nghĩa
    assert scan.market_available == 29 and scan.nflt == "ht_id=204;distance=3000"


async def test_autoextended_hotels_are_counted_not_recorded(db: AsyncSession) -> None:
    area = await _area(db)
    stays = [Stay(i, 204, 3, 500_000 + i, 2) for i in range(5)]
    stays += [Stay(100 + i, 204, 3, 400_000, 4, autoextended=True) for i in range(3)]
    world = World(stays)
    await _svc(db, world).scan_night(_target(area, rungs=()), NIGHT, enumerate_ids=True)
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.properties_found, scan.autoextended, scan.low_availability) == (5, 3, True)
    assert scan.hotels_seen == 5 and await _count(db, MarketAreaHotel) == 5


async def test_request_cap_marks_capped_and_keeps_partial(db: AsyncSession) -> None:
    area = await _area(db, segment_nflt="ht_id=204")
    world = World(default_world())
    result = await _svc(db, world).scan_night(
        _target(area, max_requests=4), NIGHT, enumerate_ids=True
    )
    assert (result.status, result.pages, result.error) == ("capped", 4, None)
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    # Hết trần giữa lúc đếm thang: không lưu thang thiếu nấc; danh sách mới có trang đầu.
    assert (scan.status, scan.hotels_seen, scan.enumerated, scan.ladder) == (
        "capped",
        100,
        False,
        None,
    )

    # Trần đủ cho thang nhưng không đủ lật id: thang đủ nấc, danh sách đủ, `enumerated` False.
    area2 = await _area(db, name="cap 9", dest_id="-2", segment_nflt="ht_id=204")
    result2 = await _svc(db, World(default_world())).scan_night(
        _target(area2, max_requests=9), NIGHT, enumerate_ids=True
    )
    scan2 = await db.get(MarketListScan, result2.scan_id)
    assert scan2 is not None and (scan2.status, scan2.hotels_seen, scan2.enumerated) == (
        "capped",
        189,
        False,
    )
    assert scan2.ladder is not None and set(scan2.ladder) == {"2", "5", "10", "20", "30"}


async def test_blocked_retries_once_then_stops(db: AsyncSession) -> None:
    area = await _area(db)
    world = World(default_world(10))
    world.fail = [ListingBlocked("graphql search blocked (http 403)")] * 2
    result = await _svc(db, world).scan_night(_target(area), NIGHT)
    assert (result.status, result.error, result.pages) == ("blocked", "blocked", 2)
    assert await _count(db, Hotel) == 0


async def test_wrong_dates_count_as_blocked(db: AsyncSession) -> None:
    area = await _area(db)
    world = World(default_world(10), night=NIGHT + timedelta(days=1))
    result = await _svc(db, world).scan_night(_target(area), NIGHT)
    assert (result.status, result.error) == ("blocked", "blocked: wrong dates")
    assert len(world.inputs) == 2


async def test_schema_error_falls_back_to_ssr_first_page(db: AsyncSession) -> None:
    area = await _area(db, name="Ho Chi Minh City", dest_id="-3730078")
    world = World(default_world(10), night=date(2026, 10, 9))
    # Lỗi GraphQL được hỏi lại một lần (có lúc chỉ tạm thời); lỗi lần hai mới dự phòng SSR.
    world.fail = [json.dumps({"errors": [{"message": "Cannot query field"}], "data": None})] * 2
    path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "searchresults_hcmc_2026-10-09.html.gz"
    )
    world.ssr_html = gzip.decompress(path.read_bytes()).decode("utf-8")
    result = await _svc(db, world).scan_night(_target(area), date(2026, 10, 9), enumerate_ids=True)
    assert (result.status, result.source, result.pages) == ("completed", "ssr", 3)
    scan = (await db.execute(select(MarketListScan))).scalar_one()
    assert (scan.properties_found, scan.hotels_seen, scan.unavailability_pct) == (3944, 25, 21)
    assert scan.ladder is None and scan.enumerated is False
    assert "dest_id=-3730078" in world.urls[0]


class _Collector:
    def __init__(self, world: World) -> None:
        self._world = world

    async def search_graphql(self, payload: dict[str, Any], referer: str) -> str:
        return await self._world.search_graphql(payload, referer)

    async def search_page(self, url: str) -> str:
        return await self._world.search_page(url)


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


async def test_job_chains_nights_enumerates_near_nights_and_stops_when_blocked(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        jobs, "MarketListService", functools.partial(MarketListService, backoff=_no_sleep)
    )
    settings = get_settings().model_copy(
        update={"market_enumerate_nights": 1, "market_ladder_rungs": "2,5"}
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    area = await _area(db, list_nights=3)
    ts = int(area.list_requested_at.timestamp())  # type: ignore[union-attr]
    world = World([Stay(i, 204, 3, 900_000 + i, 1 + i % 6) for i in range(12)])
    queue, pauses = _Queue(), MemoryChannelPauses(lambda: NOW)
    ctx = {
        "deps": _Deps(db),
        "collector": _Collector(world),
        "channel": "booking",
        "queue": queue,
        "pauses": pauses,
    }

    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 0, ts) == "completed"
    assert queue.market == [(area.id, "booking", NIGHT.isoformat(), 1, ts)]
    night0 = (await db.execute(select(MarketListScan))).scalar_one()
    assert night0.enumerated is True and set(night0.ladder or {}) == {"2", "5"}

    world.night = NIGHT + timedelta(days=1)
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 1, ts) == "completed"
    night1 = (
        await db.execute(select(MarketListScan).where(MarketListScan.stay_date == world.night))
    ).scalar_one()
    assert night1.enumerated is False  # ngoài số đêm liệt kê id: chỉ đếm
    assert all(i["pagination"]["rowsPerPage"] == 1 for i in world.inputs[-2:])

    world.fail = [ListingBlocked("http 429")] * 2
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 2, ts) == "blocked"
    await db.refresh(area)
    assert (area.last_list_status, area.last_list_error) == ("blocked", "blocked")
    assert await pauses.is_paused("booking:market") and not await pauses.is_paused("booking")
    assert len(queue.market) == 2
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 1, ts - 3600) == "superseded"


async def test_job_skips_collectors_without_graphql_search(db: AsyncSession) -> None:
    area = await _area(db)

    class _Old:
        async def search_page(self, url: str) -> str:
            raise AssertionError("not called")

    ctx = {
        "deps": _Deps(db),
        "collector": _Old(),
        "channel": "booking",
        "queue": _Queue(),
        "pauses": MemoryChannelPauses(lambda: NOW),
    }
    assert await scan_market_list(ctx, area.id, NIGHT.isoformat(), 0) == "unsupported"


async def test_gap_fill_by_price_only_when_popular_pages_miss_over_2_percent(
    db: AsyncSession,
) -> None:
    area = await _area(db)
    stays = [Stay(i, 204, 3, 900_000 + i, 1) for i in range(150)]
    world = World(stays)
    world.hidden_popular = {5}  # thiếu 1/150: bỏ qua, không lật lại cả danh sách theo giá
    result = await _svc(db, world).scan_night(_target(area, rungs=()), NIGHT)
    assert (result.pages, result.hotels_seen) == (2, 149)
    assert all(i["sorters"]["selectedSorter"] is None for i in world.inputs)

    area2 = await _area(db, name="other", dest_id="-1")
    world2 = World(stays)
    world2.hidden_popular = set(range(0, 150, 10))  # thiếu 15/150 = 10%: lấp theo giá
    result2 = await _svc(db, world2).scan_night(_target(area2, rungs=()), NIGHT)
    assert result2.hotels_seen == 150
    assert [i["sorters"]["selectedSorter"] for i in world2.inputs] == [None, None, "price", "price"]
    ranks = (
        (
            await db.execute(
                select(MarketListPrice.rank).where(MarketListPrice.scan_id == result2.scan_id)
            )
        )
        .scalars()
        .all()
    )
    assert sum(1 for r in ranks if r is None) == 15  # lấp theo giá: không có hạng


async def test_transient_graphql_error_is_retried_without_ssr_fallback(db: AsyncSession) -> None:
    area = await _area(db)
    world = World(default_world(10))
    world.fail = [json.dumps({"errors": [{"message": "Internal server error"}], "data": None})]
    result = await _svc(db, world).scan_night(_target(area, rungs=()), NIGHT)
    assert (result.status, result.source, result.pages) == ("completed", "graphql", 2)
    assert world.urls == []  # không cần trang SSR


async def test_enumeration_over_booking_cap_is_not_marked_enumerated(db: AsyncSession) -> None:
    area = await _area(db)
    world = World([Stay(i, 204, 3, 500_000 + i, 1 + i % 4) for i in range(1050)])
    result = await _svc(db, world).scan_night(
        _target(area, max_requests=100, rungs=(2,)), NIGHT, enumerate_ids=True
    )
    scan = await db.get(MarketListScan, result.scan_id)
    assert scan is not None and scan.properties_found == 1050
    # Booking chỉ trả 1.000 kết quả: danh sách và nấc 2 không liệt kê đủ → không có khoảng phòng.
    assert (scan.hotels_seen, scan.enumerated) == (1000, False)
    assert scan.ladder is not None and scan.ladder["2"]["available"] == 787


async def test_interleaved_autoextended_results_do_not_cut_the_list_short(
    db: AsyncSession,
) -> None:
    area = await _area(db)
    stays = [Stay(i, 204, 3, 500_000 + i, 4) for i in range(300)]
    stays += [Stay(1000 + i, 204, 3, 450_000, 4, autoextended=True) for i in range(100)]
    world = World(stays)
    world.interleave = 3  # 3 thẻ trong khu vực, 1 thẻ nới thêm, …
    result = await _svc(db, world).scan_night(_target(area, rungs=(2,)), NIGHT, enumerate_ids=True)
    scan = await db.get(MarketListScan, result.scan_id)
    assert scan is not None
    assert (scan.properties_found, scan.autoextended, scan.hotels_seen) == (300, 100, 300)
    assert scan.enumerated is True and await _count(db, MarketAreaHotel) == 300
