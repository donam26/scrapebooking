"""Radar cạnh tranh (roadmap Phase 4): khuyến mãi, hạn chế bán, chính sách huỷ của từng đối thủ và
mức khan phòng của khu vực — đọc từ dữ liệu đã quét, không tốn request mới."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantDep
from app.api.hotel_views import tenant_channel
from app.db.models import AvailabilityEvent, Hotel, HotelDateMetric, Tenant, TenantHotel
from app.market.pace_report import tenant_today
from app.market.radar import (
    area_scarcity,
    cancellation_profile,
    promo_runs,
    promo_share_by_night,
    restriction_for,
)
from app.marketscan.models import MarketArea, MarketListScan

router = APIRouter(prefix="/market/radar", tags=["radar"])

MAX_NIGHTS = 120


class PromoRunOut(BaseModel):
    label: str
    origin: str | None  # channel (Booking tự áp: Genius, chỉ trên app…) | hotel (khách sạn bật)
    nights: list[date]
    max_depth_pct: Decimal | None
    started_at: datetime | None


class HotelPromosOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    promos: list[PromoRunOut]


class PromoNightOut(BaseModel):
    stay_date: date
    running: int  # số đối thủ đang chạy KM
    observed: int


class PromotionsOut(BaseModel):
    channel: str
    start: date
    end: date
    hotels: list[HotelPromosOut]
    nights: list[PromoNightOut]


class RestrictionNightOut(BaseModel):
    stay_date: date
    min_stay: int
    closed_to_arrival: bool


class HotelRestrictionsOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    nights: list[RestrictionNightOut]  # chỉ đêm có hạn chế


class RestrictionsOut(BaseModel):
    channel: str
    start: date
    end: date
    hotels: list[HotelRestrictionsOut]


class CancellationOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    nights_priced: int
    refundable_share: Decimal | None  # % đêm có gói huỷ miễn phí
    nonrefundable_nights: int
    nr_discount_pct: Decimal | None  # trung vị mức giảm NR so với gói linh hoạt cùng bữa sáng
    pairs: int


class CancellationsOut(BaseModel):
    channel: str
    start: date
    end: date
    hotels: list[CancellationOut]


class AreaNightOut(BaseModel):
    stay_date: date
    properties: int | None
    scanned_at: datetime | None
    lead_days: int | None
    week_ago: int | None
    change_pct: Decimal | None


class AreaScarcityOut(BaseModel):
    area_id: int
    area_name: str
    nights: list[AreaNightOut]


async def _window(
    session: AsyncSession, tenant_id: int, start: date | None, end: date | None, days: int
) -> tuple[date, date]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    s = start or tenant_today(tenant)
    e = end or s + timedelta(days=days - 1)
    if e < s or (e - s).days >= MAX_NIGHTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_NIGHTS} nights"
        )
    return s, e


async def _hotels(session: AsyncSession, tenant_id: int) -> list[tuple[int, str | None, str]]:
    rows = await session.execute(
        select(TenantHotel.hotel_id, TenantHotel.label, Hotel.name, TenantHotel.role)
        .join(Hotel, Hotel.id == TenantHotel.hotel_id)
        .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
        .order_by(case((TenantHotel.role == "self", 0), else_=1), TenantHotel.added_at)
    )
    return [(h, label or name, role) for h, label, name, role in rows]


async def _metrics(
    session: AsyncSession, ids: list[int], channel: str, s: date, e: date
) -> dict[int, list[HotelDateMetric]]:
    out: dict[int, list[HotelDateMetric]] = defaultdict(list)
    if not ids:
        return out
    for m in (
        await session.execute(
            select(HotelDateMetric).where(
                HotelDateMetric.hotel_id.in_(ids),
                HotelDateMetric.channel == channel,
                HotelDateMetric.stay_date >= s,
                HotelDateMetric.stay_date <= e,
            )
        )
    ).scalars():
        out[m.hotel_id].append(m)
    return out


@router.get("/promotions", response_model=PromotionsOut)
async def promotions(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> PromotionsOut:
    """Radar khuyến mãi (4.1): đối thủ nào chạy KM gì, sâu bao nhiêu, bao nhiêu đêm, từ bao giờ."""
    s, e = await _window(session, tenant_id, start, end, 30)
    ch = tenant_channel()
    hotels = await _hotels(session, tenant_id)
    ids = [h for h, _, _ in hotels]
    metrics = await _metrics(session, ids, ch, s, e)
    starts: dict[int, dict[str, datetime]] = defaultdict(dict)
    if ids:
        for hid, labels, at in await session.execute(
            select(
                AvailabilityEvent.hotel_id,
                AvailabilityEvent.to_value,
                AvailabilityEvent.observed_at,
            )
            .where(
                AvailabilityEvent.hotel_id.in_(ids),
                AvailabilityEvent.channel == ch,
                AvailabilityEvent.event_type == "promo_start",
                AvailabilityEvent.observed_at >= datetime.now(tz=UTC) - timedelta(days=30),
            )
            .order_by(AvailabilityEvent.observed_at)
        ):
            for label in (labels or "").split(", "):
                if label:
                    starts[hid].setdefault(label, at)
    by_hotel = {
        h: {
            m.stay_date: m.promos
            for m in metrics.get(h, [])
            if m.availability_status == "available"
        }
        for h in ids
    }
    nights = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    share = promo_share_by_night(
        [by_hotel[h] for h, _, role in hotels if role == "competitor"], nights
    )
    return PromotionsOut(
        channel=ch,
        start=s,
        end=e,
        hotels=[
            HotelPromosOut(
                hotel_id=h,
                name=name,
                role=role,
                promos=[PromoRunOut(**r.__dict__) for r in promo_runs(by_hotel[h], starts.get(h))],
            )
            for h, name, role in hotels
        ],
        nights=[PromoNightOut(stay_date=d, running=a, observed=b) for d, (a, b) in share.items()],
    )


@router.get("/restrictions", response_model=RestrictionsOut)
async def restrictions(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> RestrictionsOut:
    """Radar hạn chế (4.2): số đêm tối thiểu, không nhận khách ngày đến."""
    s, e = await _window(session, tenant_id, start, end, 60)
    ch = tenant_channel()
    hotels = await _hotels(session, tenant_id)
    metrics = await _metrics(session, [h for h, _, _ in hotels], ch, s, e)
    out = []
    for h, name, role in hotels:
        rows = []
        for m in sorted(metrics.get(h, []), key=lambda x: x.stay_date):
            r = restriction_for(m.stay_date, m.min_stay, m.availability_status)
            if r.any:
                rows.append(
                    RestrictionNightOut(
                        stay_date=m.stay_date,
                        min_stay=r.min_stay,
                        closed_to_arrival=r.closed_to_arrival,
                    )
                )
        out.append(HotelRestrictionsOut(hotel_id=h, name=name, role=role, nights=rows))
    return RestrictionsOut(channel=ch, start=s, end=e, hotels=out)


@router.get("/cancellation", response_model=CancellationsOut)
async def cancellation(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> CancellationsOut:
    """Chính sách huỷ (4.3): % đêm có gói linh hoạt, mức giảm của gói không hoàn huỷ."""
    s, e = await _window(session, tenant_id, start, end, 30)
    ch = tenant_channel()
    hotels = await _hotels(session, tenant_id)
    metrics = await _metrics(session, [h for h, _, _ in hotels], ch, s, e)
    out = []
    for h, name, role in hotels:
        p = cancellation_profile(
            m.prices_by_key for m in metrics.get(h, []) if m.availability_status == "available"
        )
        out.append(
            CancellationOut(
                hotel_id=h,
                name=name,
                role=role,
                nights_priced=p.nights_priced,
                refundable_share=p.refundable_share,
                nonrefundable_nights=p.nights_with_nonrefundable,
                nr_discount_pct=p.nr_discount_pct,
                pairs=p.pairs,
            )
        )
    return CancellationsOut(channel=ch, start=s, end=e, hotels=out)


@router.get("/area-scarcity", response_model=AreaScarcityOut)
async def area_scarcity_view(
    tenant_id: TenantDep,
    session: SessionDep,
    area_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
) -> AreaScarcityOut:
    """Chỉ số khan phòng khu vực (4.4): số chỗ ở còn phòng kênh báo theo đêm, so 7 ngày trước."""
    s, e = await _window(session, tenant_id, start, end, 30)
    stmt = select(MarketArea).where(MarketArea.tenant_id == tenant_id)
    stmt = stmt.where(MarketArea.id == area_id) if area_id else stmt.order_by(MarketArea.id)
    area = (await session.execute(stmt.limit(1))).scalar_one_or_none()
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market area not found")
    scans = [
        (d, at, n)
        for d, at, n in await session.execute(
            select(
                MarketListScan.stay_date,
                MarketListScan.scanned_at,
                MarketListScan.properties_found,
            ).where(
                MarketListScan.area_id == area.id,
                MarketListScan.stay_date >= s,
                MarketListScan.stay_date <= e,
                MarketListScan.status == "completed",
            )
        )
    ]
    nights = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    return AreaScarcityOut(
        area_id=area.id,
        area_name=area.name,
        nights=[AreaNightOut(**n.__dict__) for n in area_scarcity(scans, nights)],
    )
