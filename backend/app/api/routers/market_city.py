"""Thị trường toàn thành phố: khu vực theo dõi (CRUD, quét ngay), số liệu cả chợ một đêm, bảng khách
sạn của khu vực để chọn đối thủ. Khu vực thuộc tenant; khách sạn dùng chung toàn hệ thống."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, SettingsDep, TenantDep, WriterDep
from app.api.market_city_schemas import (
    CityAreaOut,
    CityDetailOut,
    CityHotelOut,
    CityHotelsOut,
    CityListOut,
    DestinationOut,
    MarketAreaCreate,
    MarketAreaOut,
    MarketAreaUpdate,
    MarketCityOut,
    PriceBucketOut,
    ScanNowOut,
)
from app.collector.budget import RedisRequestBudget
from app.collector.proxy import StaticProxyProvider
from app.config import Settings
from app.db.models import Tenant
from app.logging import get_logger
from app.market.pace_report import tenant_today
from app.marketscan import city as C
from app.marketscan.destinations import BookingDestinationSearch, DestinationSearch
from app.marketscan.limits import SearchThrottle, clamp_config
from app.marketscan.models import MarketArea, MarketAreaHotel
from app.marketscan.rounds import ListQueue, market_pause_key, start_round
from app.marketscan.slices import COVERAGE_TARGET
from app.marketscan.stats import price_stats
from app.scheduler.channel_pause import ChannelPauses, RedisChannelPauses

log = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["market-city"])

SCAN_NOW_DEDUP = timedelta(minutes=10)
RUNNING_GRACE = timedelta(minutes=30)  # vòng đang chạy (có tiến triển gần đây): không mở vòng mới


def _redis(request: Request) -> Any | None:
    return getattr(getattr(request.app.state, "queue", None), "redis", None)


def _pauses(request: Request) -> ChannelPauses | None:
    override: ChannelPauses | None = getattr(request.app.state, "pauses", None)
    if override is not None:
        return override
    redis = _redis(request)
    return RedisChannelPauses(redis) if redis is not None else None


def _throttle(request: Request, settings: Settings) -> SearchThrottle:
    throttle: SearchThrottle | None = getattr(request.app.state, "market_search_throttle", None)
    if throttle is None:
        throttle = SearchThrottle(settings.market_search_per_minute)
        request.app.state.market_search_throttle = throttle
    return throttle


def get_destination_search(request: Request, settings: SettingsDep) -> DestinationSearch:
    """Gọi autocomplete qua proxy của hệ thống (test thay bằng app.state.destination_search)."""
    override: DestinationSearch | None = getattr(request.app.state, "destination_search", None)
    if override is not None:
        return override
    try:
        proxies = StaticProxyProvider(settings.proxy_templates)
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "proxy not configured") from exc
    redis = _redis(request)
    budget = (
        RedisRequestBudget(redis, "booking", settings.channel_budget("booking")) if redis else None
    )
    return BookingDestinationSearch(proxies, budget)


SearchDep = Annotated[DestinationSearch, Depends(get_destination_search)]


async def _area(session: AsyncSession, tenant_id: int, area_id: int | None) -> MarketArea:
    stmt = select(MarketArea).where(MarketArea.tenant_id == tenant_id)
    if area_id is not None:
        stmt = stmt.where(MarketArea.id == area_id)
    else:
        stmt = stmt.order_by(MarketArea.active.desc(), MarketArea.id).limit(1)
    area = (await session.execute(stmt)).scalar_one_or_none()
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market area not found")
    return area


async def _out(session: AsyncSession, area: MarketArea) -> MarketAreaOut:
    out = MarketAreaOut.model_validate(area)
    out.hotels_total = await C.hotels_total(session, area.id)
    return out


@router.get("/areas/search", response_model=list[DestinationOut])
async def search_destinations(
    request: Request,
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    search: SearchDep,
    q: str = Query(min_length=2, max_length=100),
) -> list[DestinationOut]:
    """Tìm thành phố/quận trên Booking (gọi thật qua proxy, tính vào ngân sách request của kênh)
    → dest_id/dest_type để tạo khu vực. Tối đa MARKET_SEARCH_PER_MINUTE lần/phút mỗi tenant."""
    if not await _throttle(request, settings).allow(tenant_id, _redis(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many destination searches, retry in a minute"
        )
    tenant = await session.get(Tenant, tenant_id)
    try:
        found = await search(q, tenant.country_code if tenant else "vn")
    except Exception as exc:  # noqa: BLE001 — proxy/mạng lỗi hoặc kênh chặn: báo thử lại
        log.warning("market_destination_search_failed", error=repr(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "booking unreachable, retry") from exc
    return [DestinationOut.model_validate(d) for d in found]


@router.get("/areas", response_model=list[MarketAreaOut])
async def list_areas(tenant_id: TenantDep, session: SessionDep) -> list[MarketAreaOut]:
    areas = list(
        (
            await session.execute(
                select(MarketArea).where(MarketArea.tenant_id == tenant_id).order_by(MarketArea.id)
            )
        ).scalars()
    )
    counts: dict[int, int] = {
        area_id: n
        for area_id, n in await session.execute(
            select(MarketAreaHotel.area_id, func.count())
            .where(MarketAreaHotel.area_id.in_([a.id for a in areas]))
            .group_by(MarketAreaHotel.area_id)
        )
    }
    return [
        MarketAreaOut.model_validate(a).model_copy(update={"hotels_total": counts.get(a.id, 0)})
        for a in areas
    ]


@router.post("/areas", response_model=MarketAreaOut, status_code=status.HTTP_201_CREATED)
async def create_area(
    body: MarketAreaCreate,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MarketAreaOut:
    count = (
        await session.execute(
            select(func.count()).select_from(MarketArea).where(MarketArea.tenant_id == tenant_id)
        )
    ).scalar_one()
    cap = settings.market_max_areas_per_tenant
    if not principal.is_operator and count >= cap:
        raise HTTPException(status.HTTP_409_CONFLICT, f"at most {cap} market areas per tenant")
    area = MarketArea(tenant_id=tenant_id, active=True, **clamp_config(body.model_dump(), settings))
    session.add(area)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "market area already exists") from exc
    await session.refresh(area)
    return await _out(session, area)


@router.patch("/areas/{area_id}", response_model=MarketAreaOut)
async def update_area(
    area_id: int,
    body: MarketAreaUpdate,
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MarketAreaOut:
    area = await _area(session, tenant_id, area_id)
    for key, value in clamp_config(body.model_dump(exclude_unset=True), settings).items():
        if value is not None:
            setattr(area, key, value)
    await session.commit()
    await session.refresh(area)
    return await _out(session, area)


@router.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(
    area_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> None:
    """Xoá khu vực cùng danh sách/giá đã quét (khách sạn và dữ liệu quét chi tiết vẫn giữ)."""
    area = await _area(session, tenant_id, area_id)
    await session.delete(area)
    await session.commit()


@router.post(
    "/areas/{area_id}/scan-now", response_model=ScanNowOut, status_code=status.HTTP_202_ACCEPTED
)
async def scan_area_now(
    area_id: int, request: Request, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> ScanNowOut:
    """Mở vòng quét danh sách mới (đẩy job sau khi đã ghi yêu cầu). Không mở khi vừa có yêu cầu
    trong 10 phút hoặc vòng hiện tại đang chạy; kênh đang tạm dừng vì bị chặn thì từ chối."""
    area = await _area(session, tenant_id, area_id)
    if not area.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "market area is inactive")
    queue: ListQueue | None = getattr(request.app.state, "queue", None)
    if queue is None or not hasattr(queue, "enqueue_market_list"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable")
    now = datetime.now(tz=UTC)
    running = (
        area.last_list_status == "running"
        and area.last_list_scan_at is not None
        and now - area.last_list_scan_at < RUNNING_GRACE
    )
    if running:
        return ScanNowOut(area_id=area.id, enqueued=False, list_requested_at=area.list_requested_at)
    pauses = _pauses(request)
    if pauses is not None and (
        await pauses.is_paused(area.channel)
        or await pauses.is_paused(market_pause_key(area.channel))
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "channel paused after blocking, retry in a few minutes"
        )
    tenant = await session.get(Tenant, tenant_id)
    start = tenant_today(tenant) if tenant else now.date()
    try:
        enqueued = await start_round(session, queue, area, now, now - SCAN_NOW_DEDUP, start)
    except Exception as exc:  # noqa: BLE001 — Redis lỗi: yêu cầu đã được trả lại
        log.warning("market_scan_now_enqueue_failed", area_id=area.id, error=repr(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable") from exc
    await session.refresh(area)
    return ScanNowOut(area_id=area.id, enqueued=enqueued, list_requested_at=area.list_requested_at)


NightQuery = Annotated[date | None, Query(alias="date", description="Đêm (mặc định hôm nay)")]


async def _night(session: AsyncSession, tenant_id: int, night: date | None) -> date:
    if night is not None:
        return night
    tenant = await session.get(Tenant, tenant_id)
    return tenant_today(tenant) if tenant else datetime.now(tz=UTC).date()


@router.get("/city", response_model=MarketCityOut)
async def market_city(
    tenant_id: TenantDep,
    session: SessionDep,
    settings: SettingsDep,
    night: NightQuery = None,
    area_id: int | None = None,
) -> MarketCityOut:
    area = await _area(session, tenant_id, area_id)
    stay = await _night(session, tenant_id, night)
    now = datetime.now(tz=UTC)
    scan = await C.latest_list_scan(session, area.id, stay)
    currency = settings.scan_currency
    prices = (
        [
            p
            for _, p, cur in (await C.scan_prices(session, scan.id)).values()
            if p and cur == currency
        ]
        if scan is not None
        else []
    )
    stats = price_stats(prices)
    coverage = C.list_coverage(scan)
    detail = await C.detail_summary(session, area, stay, now)
    return MarketCityOut(
        stay_date=stay,
        channel=area.channel,
        area=CityAreaOut(
            id=area.id,
            name=area.name,
            last_list_scan_at=area.last_list_scan_at,
            last_detail_scan_at=area.last_detail_scan_at,
            hotels_total=await C.hotels_total(session, area.id),
        ),
        list_scan=CityListOut(
            scan_id=scan.id if scan else None,
            status=scan.status if scan else None,
            scanned_at=scan.scanned_at if scan else None,
            finished_at=scan.finished_at if scan else None,
            pages=scan.pages if scan else 0,
            properties_found=scan.properties_found if scan else None,
            hotels_seen=scan.hotels_seen if scan else 0,
            coverage=round(coverage, 4) if coverage is not None else None,
            sample=coverage is None or coverage < COVERAGE_TARGET,
            priced=stats.count,
            currency=currency,
            avg=stats.avg,
            median=stats.median,
            p25=stats.p25,
            p75=stats.p75,
            min=stats.min,
            max=stats.max,
            histogram=[PriceBucketOut(lo=b.lo, hi=b.hi, count=b.count) for b in stats.histogram],
        ),
        detail=CityDetailOut(**detail.__dict__),
    )


@router.get("/city/hotels", response_model=CityHotelsOut)
async def market_city_hotels(
    tenant_id: TenantDep,
    session: SessionDep,
    night: NightQuery = None,
    area_id: int | None = None,
    sort: Literal["review_count", "review_score", "price", "distance", "rank"] = "review_count",
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> CityHotelsOut:
    area = await _area(session, tenant_id, area_id)
    stay = await _night(session, tenant_id, night)
    total, rows = await C.city_hotels(
        session,
        tenant_id,
        area,
        stay,
        datetime.now(tz=UTC),
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return CityHotelsOut(
        stay_date=stay,
        area_id=area.id,
        total=total,
        items=[CityHotelOut(**r.__dict__) for r in rows],
    )
