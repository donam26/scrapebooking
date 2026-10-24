"""Số liệu thị trường của một khu vực cho một đêm (đọc DB, dùng cho API).

- Danh sách: lượt quét mới nhất của đêm đó (số chỗ còn phòng kênh báo, giá trên thẻ, thang phòng
  trống, khoảng phòng còn từng khách sạn).
- Chi tiết: chỉ số mới nhất (hotel_date_metrics) và công suất ước tính đủ tin cậy
  (occupancy_estimates) của khách sạn trong khu vực, từ các run quét chi tiết/run thường.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, case, func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelDateMetric, Listing, TenantHotel
from app.market.models import OccupancyEstimate
from app.market.occupancy import Q4, is_reliable
from app.marketscan.graphql import combine_nflt, radius_nflt
from app.marketscan.ladder import hotel_range, percentile_rank
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan

COVERAGE_TARGET = 0.98  # danh sách thấy ≥ 98% số kênh báo: coi như đủ (giá không còn là mẫu)
EARTH_KM = 6371.0
FRESH = timedelta(days=4)  # quan sát chi tiết cũ hơn không tính (tầng xa quét lại sau ≤ 66 giờ)
SEGMENT_WINDOW = timedelta(days=30)  # mẫu số phân khúc: số còn phòng lớn nhất trong 30 ngày quét


@dataclass(frozen=True)
class DetailSummary:
    hotels_with_data: int
    hotels_available: int
    hotels_sold_out: int
    rooms_left_known_sum: int
    inventory_sum: int
    occupancy_est: Decimal | None
    coverage_hotels: int
    last_observed_at: datetime | None


@dataclass(frozen=True)
class CityHotel:
    hotel_id: int
    name: str | None
    url: str | None
    image_url: str | None
    review_score: Decimal | None
    review_count: int | None
    stars: Decimal | None
    district: str | None
    distance_km: float | None
    price: Decimal | None
    currency: str | None
    available: bool | None
    rank: int | None
    watched: bool
    role: str | None
    rooms_min: int | None = None
    rooms_max: int | None = None
    only_left: int | None = None


@dataclass(frozen=True)
class ScanEntry:
    rank: int | None
    price: Decimal | None
    currency: str | None
    rooms_min: int | None
    only_left: int | None


@dataclass(frozen=True)
class SelfHotel:
    hotel_id: int
    name: str | None
    lat: float | None
    lng: float | None


@dataclass(frozen=True)
class SelfMarket:
    hotel_id: int
    name: str | None
    in_area: bool
    rank: int | None
    price: Decimal | None
    currency: str | None
    price_percentile: int | None
    rooms_min: int | None
    rooms_max: int | None
    rooms_percentile: int | None
    only_left: int | None
    rooms_left_min: int | None
    rooms_left_max: int | None


def _area_hotel_ids(area_id: int) -> Select[tuple[int]]:
    return select(MarketAreaHotel.hotel_id).where(MarketAreaHotel.area_id == area_id)


async def hotels_total(s: AsyncSession, area_id: int) -> int:
    return int(
        (
            await s.execute(
                select(func.count())
                .select_from(MarketAreaHotel)
                .where(MarketAreaHotel.area_id == area_id)
            )
        ).scalar_one()
    )


def list_coverage(scan: MarketListScan | None) -> float | None:
    """Phần khách sạn đã thấy trên số chỗ ở còn phòng kênh báo (0–1). Dưới 98%: giá là mẫu, và
    khách sạn vắng mặt không được hiểu là hết phòng."""
    if scan is None or not scan.properties_found:
        return None
    return min(1.0, scan.hotels_seen / scan.properties_found)


def area_scope(area: MarketArea) -> str | None:
    """Bộ lọc hiện tại của khu vực (phân khúc + bán kính) — so với `market_list_scans.nflt`."""
    return combine_nflt(area.segment_nflt, radius_nflt(area.radius_m))


def scan_rungs(scan: MarketListScan | None) -> tuple[int, ...]:
    """Các nấc chính lượt quét đã hỏi (không lấy cấu hình hiện tại: đổi cấu hình nấc không làm
    sai khoảng phòng của lượt cũ)."""
    if scan is None or not scan.ladder:
        return ()
    return tuple(sorted(int(k) for k in scan.ladder if str(k).isdigit()))


def _usable(area: MarketArea) -> list[ColumnElement[bool]]:
    """Lượt quét dùng được của khu vực: cùng phạm vi hiện tại (đổi phân khúc/bán kính thì số cũ
    không hiện) và đã xong hoặc có ít nhất một thẻ."""
    return [
        MarketListScan.area_id == area.id,
        MarketListScan.nflt.is_not_distinct_from(area_scope(area)),
        or_(MarketListScan.status == "completed", MarketListScan.hotels_seen > 0),
    ]


def _best_first() -> list[ColumnElement[Any]]:
    """Ưu tiên lượt đủ (xong, hoặc hết trần), rồi lượt có thang, rồi nguồn GraphQL (dự phòng SSR và
    lượt trước 0018 chỉ có trang đầu), rồi mới nhất. Dùng CASE để NULL không đứng đầu khi DESC."""
    return [
        case((MarketListScan.status.in_(("completed", "capped")), 1), else_=0).desc(),
        case((MarketListScan.ladder.is_not(None), 1), else_=0).desc(),
        case((MarketListScan.source == "graphql", 1), else_=0).desc(),
        MarketListScan.scanned_at.desc(),
        MarketListScan.id.desc(),
    ]


async def latest_list_scan(s: AsyncSession, area: MarketArea, night: date) -> MarketListScan | None:
    """Lượt quét tốt nhất của đêm (xem `_best_first`)."""
    return (
        await s.execute(
            select(MarketListScan)
            .where(*_usable(area), MarketListScan.stay_date == night)
            .order_by(*_best_first())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_scans(
    s: AsyncSession, area: MarketArea, start: date, nights: int
) -> dict[date, MarketListScan]:
    """Lượt quét tốt nhất (như `latest_list_scan`) của từng đêm trong [start, start + nights)."""
    rows = await s.execute(
        select(MarketListScan)
        .where(
            *_usable(area),
            MarketListScan.stay_date >= start,
            MarketListScan.stay_date < start + timedelta(days=nights),
        )
        .order_by(MarketListScan.stay_date, *_best_first())
        .distinct(MarketListScan.stay_date)
    )
    return {scan.stay_date: scan for scan in rows.scalars()}


async def segment_base(s: AsyncSession, area: MarketArea, now: datetime) -> int | None:
    """Mẫu số phân khúc: số còn phòng lớn nhất các lượt quét 30 ngày qua CÙNG phạm vi hiện tại
    (phân khúc + bán kính) — cận dưới của tổng số khách sạn của phân khúc."""
    return (
        await s.execute(
            select(func.max(MarketListScan.properties_found)).where(
                MarketListScan.area_id == area.id,
                MarketListScan.scanned_at >= now - SEGMENT_WINDOW,
                MarketListScan.source.is_not(None),
                MarketListScan.nflt.is_not_distinct_from(area_scope(area)),
            )
        )
    ).scalar_one_or_none()


async def median_prices(
    s: AsyncSession, scan_ids: Sequence[int], currency: str
) -> dict[int, Decimal]:
    if not scan_ids:
        return {}
    rows = await s.execute(
        select(
            MarketListPrice.scan_id,
            func.percentile_cont(0.5).within_group(MarketListPrice.price.asc()),
        )
        .where(
            MarketListPrice.scan_id.in_(scan_ids),
            MarketListPrice.currency == currency,
            MarketListPrice.price.is_not(None),
        )
        .group_by(MarketListPrice.scan_id)
    )
    return {sid: Decimal(str(round(m))) for sid, m in rows if m is not None}


async def scan_entries(s: AsyncSession, scan_id: int) -> dict[int, ScanEntry]:
    rows = await s.execute(
        select(
            MarketListPrice.hotel_id,
            MarketListPrice.rank,
            MarketListPrice.price,
            MarketListPrice.currency,
            MarketListPrice.rooms_min,
            MarketListPrice.only_left,
        ).where(MarketListPrice.scan_id == scan_id)
    )
    return {h: ScanEntry(*rest) for h, *rest in rows}


async def scan_prices(
    s: AsyncSession, scan_id: int
) -> dict[int, tuple[int, Decimal | None, str | None]]:
    rows = await s.execute(
        select(
            MarketListPrice.hotel_id,
            MarketListPrice.rank,
            MarketListPrice.price,
            MarketListPrice.currency,
        ).where(MarketListPrice.scan_id == scan_id)
    )
    return {h: (rank, price, cur) for h, rank, price, cur in rows}


async def _metric_status(
    s: AsyncSession,
    area: MarketArea,
    night: date,
    now: datetime,
    hotel_ids: list[int] | None = None,
) -> dict[int, tuple[str, datetime]]:
    rows = await s.execute(
        select(
            HotelDateMetric.hotel_id,
            HotelDateMetric.availability_status,
            HotelDateMetric.last_observed_at,
        ).where(
            HotelDateMetric.channel == area.channel,
            HotelDateMetric.stay_date == night,
            HotelDateMetric.last_observed_at >= now - FRESH,
            HotelDateMetric.hotel_id.in_(
                hotel_ids if hotel_ids is not None else _area_hotel_ids(area.id)
            ),
        )
    )
    return {h: (st, at) for h, st, at in rows}


async def detail_summary(
    s: AsyncSession, area: MarketArea, night: date, now: datetime
) -> DetailSummary:
    metrics = await _metric_status(s, area, night, now)
    statuses = [st for st, _ in metrics.values()]
    latest = (
        select(OccupancyEstimate)
        .where(
            OccupancyEstimate.channel == area.channel,
            OccupancyEstimate.stay_date == night,
            OccupancyEstimate.scanned_at >= now - FRESH,
            OccupancyEstimate.hotel_id.in_(_area_hotel_ids(area.id)),
        )
        .order_by(OccupancyEstimate.hotel_id, OccupancyEstimate.scanned_at.desc())
        .distinct(OccupancyEstimate.hotel_id)
    )
    left, inventory, covered = Decimal(0), 0, 0
    for est in (await s.execute(latest)).scalars():
        if not is_reliable(est.coverage, est.occ_low, est.occ_high):
            continue
        left += Decimal(est.left_low + est.left_high) / 2
        inventory += est.inventory
        covered += 1
    occ = (1 - left / inventory).quantize(Q4) if inventory > 0 else None
    return DetailSummary(
        hotels_with_data=sum(1 for st in statuses if st in ("available", "sold_out")),
        hotels_available=statuses.count("available"),
        hotels_sold_out=statuses.count("sold_out"),
        rooms_left_known_sum=int(left.to_integral_value()),
        inventory_sum=inventory,
        occupancy_est=occ,
        coverage_hotels=covered,
        last_observed_at=max((at for _, at in metrics.values()), default=None),
    )


async def self_hotel(s: AsyncSession, tenant_id: int) -> SelfHotel | None:
    """Khách sạn "của bạn" (vai trò self đầu tiên đang theo dõi), ưu tiên khách sạn có toạ độ."""
    row = (
        await s.execute(
            select(Hotel.id, Hotel.name, Hotel.lat, Hotel.lng)
            .join(TenantHotel, TenantHotel.hotel_id == Hotel.id)
            .where(
                TenantHotel.tenant_id == tenant_id,
                TenantHotel.role == "self",
                TenantHotel.active.is_(True),
            )
            .order_by(Hotel.lat.is_(None), TenantHotel.added_at)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    hotel_id, name, lat, lng = row
    return SelfHotel(
        hotel_id,
        name,
        float(lat) if lat is not None else None,
        float(lng) if lng is not None else None,
    )


async def _self_coords(s: AsyncSession, tenant_id: int) -> tuple[float, float] | None:
    me = await self_hotel(s, tenant_id)
    if me is None or me.lat is None or me.lng is None:
        return None
    return me.lat, me.lng


async def self_market(
    s: AsyncSession,
    tenant_id: int,
    area: MarketArea,
    night: date,
    scan: MarketListScan | None,
    currency: str,
    now: datetime,
) -> SelfMarket | None:
    """Khách sạn của bạn cạnh thị trường đêm đó: có trong khu vực không, hạng, giá + phân vị giá,
    khoảng phòng còn theo thang tìm kiếm + phân vị, phòng còn từ quét trang khách sạn (chỉ quan
    sát đủ mới, như phần chi tiết)."""
    me = await self_hotel(s, tenant_id)
    if me is None:
        return None
    entries = await scan_entries(s, scan.id) if scan is not None else {}
    mine = entries.get(me.hotel_id)
    metric = (
        await s.execute(
            select(HotelDateMetric).where(
                HotelDateMetric.hotel_id == me.hotel_id,
                HotelDateMetric.channel == area.channel,
                HotelDateMetric.stay_date == night,
                HotelDateMetric.last_observed_at >= now - FRESH,
            )
        )
    ).scalar_one_or_none()
    price = mine.price if mine is not None and mine.currency == currency else None
    price_currency = currency if price is not None else None
    if price is None and metric is not None and metric.min_price is not None:
        price, price_currency = metric.min_price, metric.currency
    prices = [e.price for e in entries.values() if e.price is not None and e.currency == currency]
    enumerated = scan is not None and scan.enumerated
    lo, hi = hotel_range(mine.rooms_min, scan_rungs(scan)) if enumerated and mine else (None, None)
    rooms = [Decimal(e.rooms_min) for e in entries.values() if e.rooms_min]
    return SelfMarket(
        hotel_id=me.hotel_id,
        name=me.name,
        in_area=mine is not None,
        rank=mine.rank if mine is not None else None,
        price=price,
        currency=price_currency,
        price_percentile=percentile_rank(prices, price)
        if price is not None and price_currency == currency
        else None,
        rooms_min=lo,
        rooms_max=hi,
        rooms_percentile=percentile_rank(rooms, Decimal(lo)) if lo else None,
        only_left=mine.only_left if mine is not None else None,
        rooms_left_min=metric.rooms_left_min if metric is not None else None,
        rooms_left_max=metric.rooms_left_max if metric is not None else None,
    )


def _available(
    listed: bool,
    price: Decimal | None,
    metric: str | None,
    list_complete: bool,
    rooms_min: int | None = None,
) -> bool | None:
    """Có giá trên danh sách hoặc qua một nấc thang → còn phòng; không thì theo quét chi tiết; danh
    sách đã thấy ≥ 98% số kênh báo mà không có khách sạn này → hết phòng (kênh ẩn chỗ ở hết
    phòng); còn lại: None."""
    if listed and (price is not None or rooms_min):
        return True
    if metric in ("available", "sold_out"):
        return metric == "available"
    if not listed and list_complete:
        return False
    return None


Sort = Literal["review_count", "review_score", "price", "distance", "rank"]


def _distance_km(origin: tuple[float, float]) -> ColumnElement[float]:
    """Haversine (km) từ `origin` tới toạ độ khách sạn, tính trong SQL (NULL khi thiếu toạ độ)."""
    lat0, lng0 = origin
    dlat = func.radians(Hotel.lat - lat0) / 2
    dlng = func.radians(Hotel.lng - lng0) / 2
    h = func.power(func.sin(dlat), 2) + math.cos(math.radians(lat0)) * func.cos(
        func.radians(Hotel.lat)
    ) * func.power(func.sin(dlng), 2)
    # LEAST bỏ qua NULL: phải chặn riêng khách sạn thiếu toạ độ.
    km = 2 * EARTH_KM * func.asin(func.sqrt(func.least(1.0, h)))
    return case((and_(Hotel.lat.is_not(None), Hotel.lng.is_not(None)), km), else_=null())


async def city_hotels(
    s: AsyncSession,
    tenant_id: int,
    area: MarketArea,
    night: date,
    now: datetime,
    *,
    q: str | None = None,
    sort: Sort = "review_count",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[CityHotel]]:
    """(tổng số khách sạn khớp, một trang đã sắp xếp). Lọc/sắp xếp/phân trang trong SQL."""
    scan = await latest_list_scan(s, area, night)
    origin = await _self_coords(s, tenant_id)
    dist = _distance_km(origin) if origin is not None else null()
    where = [MarketAreaHotel.area_id == area.id]
    if q:
        where.append(Hotel.name.ilike(f"%{q.strip()}%"))
    total = (
        await s.execute(
            select(func.count())
            .select_from(MarketAreaHotel)
            .join(Hotel, Hotel.id == MarketAreaHotel.hotel_id)
            .where(*where)
        )
    ).scalar_one()
    orders: dict[str, list[ColumnElement[Any]]] = {
        "review_count": [Hotel.review_count.desc().nulls_last()],
        "review_score": [
            Hotel.review_score.desc().nulls_last(),
            Hotel.review_count.desc().nulls_last(),
        ],
        "price": [MarketListPrice.price.asc().nulls_last()],
        "distance": [dist.asc().nulls_last()] if origin is not None else [],
        "rank": [MarketAreaHotel.best_rank.asc().nulls_last()],
    }
    order = orders[sort]
    rows = (
        await s.execute(
            select(
                Hotel,
                MarketAreaHotel.best_rank,
                Listing.url,
                MarketListPrice.hotel_id,
                MarketListPrice.price,
                MarketListPrice.currency,
                dist.label("distance_km"),
                MarketListPrice.rooms_min,
                MarketListPrice.only_left,
            )
            .join(MarketAreaHotel, MarketAreaHotel.hotel_id == Hotel.id)
            .outerjoin(Listing, and_(Listing.hotel_id == Hotel.id, Listing.channel == area.channel))
            .outerjoin(
                MarketListPrice,
                and_(
                    MarketListPrice.hotel_id == Hotel.id,
                    MarketListPrice.scan_id == (scan.id if scan is not None else -1),
                ),
            )
            .where(*where)
            .order_by(*order, Hotel.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    ids = [r[0].id for r in rows]
    metrics = await _metric_status(s, area, night, now, ids)
    watch = {
        h: role
        for h, role in await s.execute(
            select(TenantHotel.hotel_id, TenantHotel.role).where(
                TenantHotel.tenant_id == tenant_id,
                TenantHotel.active.is_(True),
                TenantHotel.hotel_id.in_(ids),
            )
        )
    }
    complete = (list_coverage(scan) or 0) >= COVERAGE_TARGET
    enumerated = scan is not None and scan.enumerated
    out: list[CityHotel] = []
    for hotel, best_rank, url, listed_id, price, currency, km, rooms_min, only_left in rows:
        metric = metrics.get(hotel.id)
        lo, hi = hotel_range(rooms_min, scan_rungs(scan)) if enumerated else (None, None)
        out.append(
            CityHotel(
                hotel_id=hotel.id,
                name=hotel.name,
                url=url,
                image_url=hotel.image_url,
                review_score=hotel.review_score,
                review_count=hotel.review_count,
                stars=hotel.star_rating,
                district=hotel.district,
                distance_km=round(float(km), 2) if km is not None else None,
                price=price,
                currency=currency,
                available=_available(
                    listed_id is not None,
                    price,
                    metric[0] if metric else None,
                    complete,
                    rooms_min,
                ),
                rank=best_rank,
                watched=hotel.id in watch,
                role=watch.get(hotel.id),
                rooms_min=lo,
                rooms_max=hi,
                only_left=only_left,
            )
        )
    return int(total), out
