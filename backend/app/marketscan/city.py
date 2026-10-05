"""Số liệu thị trường toàn thành phố của một khu vực cho một đêm (đọc DB, dùng cho API).

- Danh sách: lượt quét danh sách mới nhất của đêm đó (số chỗ ở còn phòng kênh báo, giá trên thẻ).
- Chi tiết: chỉ số mới nhất (hotel_date_metrics) và công suất ước tính đủ tin cậy
  (occupancy_estimates) của khách sạn trong khu vực, từ các run quét chi tiết/run thường.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, case, func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelDateMetric, Listing, TenantHotel
from app.market.models import OccupancyEstimate
from app.market.occupancy import Q4, is_reliable
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan
from app.marketscan.slices import COVERAGE_TARGET

EARTH_KM = 6371.0
FRESH = timedelta(days=4)  # quan sát chi tiết cũ hơn không tính (tầng xa quét lại sau ≤ 66 giờ)


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


async def latest_list_scan(s: AsyncSession, area_id: int, night: date) -> MarketListScan | None:
    """Lượt quét danh sách của đêm: ưu tiên lượt "completed" mới nhất; không có thì lượt mới nhất có
    ít nhất một thẻ (đang chạy/bị chặn giữa chừng)."""
    return (
        await s.execute(
            select(MarketListScan)
            .where(
                MarketListScan.area_id == area_id,
                MarketListScan.stay_date == night,
                or_(MarketListScan.status == "completed", MarketListScan.hotels_seen > 0),
            )
            .order_by(
                (MarketListScan.status == "completed").desc(),
                MarketListScan.scanned_at.desc(),
                MarketListScan.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


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


async def _self_coords(s: AsyncSession, tenant_id: int) -> tuple[float, float] | None:
    row = (
        await s.execute(
            select(Hotel.lat, Hotel.lng)
            .join(TenantHotel, TenantHotel.hotel_id == Hotel.id)
            .where(
                TenantHotel.tenant_id == tenant_id,
                TenantHotel.role == "self",
                TenantHotel.active.is_(True),
                Hotel.lat.is_not(None),
                Hotel.lng.is_not(None),
            )
            .order_by(TenantHotel.added_at)
            .limit(1)
        )
    ).first()
    return (float(row[0]), float(row[1])) if row else None


def _available(
    listed: bool,
    price: Decimal | None,
    metric: str | None,
    list_complete: bool,
) -> bool | None:
    """Có giá trên danh sách → còn phòng; không thì theo quét chi tiết; danh sách đã thấy ≥ 98%
    số kênh báo mà không có khách sạn này → hết phòng (kênh ẩn chỗ ở hết phòng); còn lại: None."""
    if listed and price is not None:
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
    scan = await latest_list_scan(s, area.id, night)
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
    out: list[CityHotel] = []
    for hotel, best_rank, url, listed_id, price, currency, km in rows:
        metric = metrics.get(hotel.id)
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
                    listed_id is not None, price, metric[0] if metric else None, complete
                ),
                rank=best_rank,
                watched=hotel.id in watch,
                role=watch.get(hotel.id),
            )
        )
    return int(total), out
