"""Uy tín và vị trí hiển thị (roadmap 7.1, 7.2; BC N4, N5): điểm/số review theo thời gian, tốc
độ review/tháng, khoảng cách tới các mốc của Booking, bản đồ giá–chất lượng, thứ hạng trên trang
kết quả (tách thẻ quảng cáo) và huy hiệu Preferred/deal — từ trang kết quả đã quét."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import case, select

from app.analytics.rules import median
from app.api.deps import SessionDep, TenantDep
from app.channels.registry import BOOKING
from app.db.models import Hotel, HotelDateMetric, TenantHotel
from app.market.models import HotelReviewSnapshot
from app.marketscan.models import MarketArea, MarketListPrice, MarketListScan

router = APIRouter(prefix="/market", tags=["reputation"])

# Mốc điểm Booking: 7,0 điều kiện Preferred; 7,5 điều kiện Genius; 8,0 Traveller Review Award;
# 9,0 nhãn "Superb".
THRESHOLDS = (Decimal("7.0"), Decimal("7.5"), Decimal("8.0"), Decimal("9.0"))


class ReputationHotelOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    review_score: Decimal | None
    review_count: int | None
    reviews_per_month: Decimal | None  # tốc độ review ≈ lượng khách lưu trú
    score_change: Decimal | None  # so với đầu cửa sổ
    next_threshold: Decimal | None
    gap_to_next: Decimal | None
    badges: list[str]
    # Bản đồ giá–chất lượng (tương quan, không phải nhân quả): chỉ số giá niêm yết và chỉ số
    # điểm so với trung vị compset (100 = ngang).
    price_index: Decimal | None
    score_index: Decimal | None


class ReputationOut(BaseModel):
    days: int
    hotels: list[ReputationHotelOut]


class VisibilityHotelOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    scans: int  # số lượt trang kết quả có khách sạn này
    avg_rank: Decimal | None  # thứ hạng hiển thị (gồm thẻ quảng cáo)
    avg_organic_rank: Decimal | None  # bỏ thẻ quảng cáo đứng trước
    best_rank: int | None
    sponsored_share: Decimal | None  # % lần xuất hiện là thẻ quảng cáo
    badges: list[str]


class VisibilityOut(BaseModel):
    area_id: int | None
    days: int
    hotels: list[VisibilityHotelOut]


async def _links(session: SessionDep, tenant_id: int) -> list[tuple[int, str | None, str]]:
    rows = await session.execute(
        select(TenantHotel.hotel_id, TenantHotel.label, Hotel.name, TenantHotel.role)
        .join(Hotel, Hotel.id == TenantHotel.hotel_id)
        .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
        .order_by(case((TenantHotel.role == "self", 0), else_=1), TenantHotel.added_at)
    )
    return [(h, label or name, role) for h, label, name, role in rows]


def review_velocity(
    series: list[tuple[date, int | None]],
) -> Decimal | None:
    """Số review mới mỗi 30 ngày từ chuỗi (ngày, tổng số review)."""
    pts = [(d, n) for d, n in series if n is not None]
    if len(pts) < 2:
        return None
    (d0, n0), (d1, n1) = pts[0], pts[-1]
    days = (d1 - d0).days
    if days <= 0:
        return None
    return (Decimal(n1 - n0) / days * 30).quantize(Decimal("0.1"))


def next_threshold(score: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if score is None:
        return None, None
    for t in THRESHOLDS:
        if score < t:
            return t, (t - score).quantize(Decimal("0.1"))
    return None, None


@router.get("/reputation", response_model=ReputationOut)
async def reputation(
    tenant_id: TenantDep, session: SessionDep, days: int = Query(90, ge=7, le=730)
) -> ReputationOut:
    links = await _links(session, tenant_id)
    ids = [h for h, _, _ in links]
    channel = BOOKING
    since = datetime.now(tz=UTC).date() - timedelta(days=days)
    series: dict[int, list[HotelReviewSnapshot]] = defaultdict(list)
    if ids:
        for r in (
            await session.execute(
                select(HotelReviewSnapshot)
                .where(
                    HotelReviewSnapshot.hotel_id.in_(ids),
                    HotelReviewSnapshot.channel == channel,
                    HotelReviewSnapshot.observed_on >= since,
                )
                .order_by(HotelReviewSnapshot.observed_on)
            )
        ).scalars():
            series[r.hotel_id].append(r)
    hotels = (
        {h.id: h for h in (await session.execute(select(Hotel).where(Hotel.id.in_(ids)))).scalars()}
        if ids
        else {}
    )
    # Giá niêm yết trung vị 30 đêm tới của từng khách sạn trên kênh tham chiếu.
    today = datetime.now(tz=UTC).date()
    prices: dict[int, list[Decimal]] = defaultdict(list)
    if ids:
        for hid, p in await session.execute(
            select(HotelDateMetric.hotel_id, HotelDateMetric.min_price).where(
                HotelDateMetric.hotel_id.in_(ids),
                HotelDateMetric.channel == channel,
                HotelDateMetric.stay_date >= today,
                HotelDateMetric.stay_date < today + timedelta(days=30),
                HotelDateMetric.availability_status == "available",
                HotelDateMetric.min_price.is_not(None),
            )
        ):
            prices[hid].append(p)
    hotel_price = {h: median(v) for h, v in prices.items() if v}
    comp = [h for h, _, role in links if role == "competitor"]
    comp_price = median(p for h in comp if (p := hotel_price.get(h)) is not None)

    def score_of(h: int) -> Decimal | None:
        s = series.get(h)
        if s and s[-1].review_score is not None:
            return Decimal(s[-1].review_score)
        hotel = hotels.get(h)
        return Decimal(hotel.review_score) if hotel and hotel.review_score is not None else None

    comp_score = median(sc for h in comp if (sc := score_of(h)) is not None)
    out = []
    for h, name, role in links:
        s = series.get(h, [])
        score = score_of(h)
        count = s[-1].review_count if s else (hotels[h].review_count if h in hotels else None)
        nxt, gap = next_threshold(score)
        first = next((x.review_score for x in s if x.review_score is not None), None)
        hp = hotel_price.get(h)
        out.append(
            ReputationHotelOut(
                hotel_id=h,
                name=name,
                role=role,
                review_score=score,
                review_count=count,
                reviews_per_month=review_velocity([(x.observed_on, x.review_count) for x in s]),
                score_change=(score - Decimal(first)).quantize(Decimal("0.1"))
                if score is not None and first is not None
                else None,
                next_threshold=nxt,
                gap_to_next=gap,
                badges=list((s[-1].badges or []) if s else []),
                price_index=(hp / comp_price * 100).quantize(Decimal("0.1"))
                if hp is not None and comp_price
                else None,
                score_index=(score / comp_score * 100).quantize(Decimal("0.1"))
                if score is not None and comp_score
                else None,
            )
        )
    return ReputationOut(days=days, hotels=out)


@router.get("/visibility", response_model=VisibilityOut)
async def visibility(
    tenant_id: TenantDep,
    session: SessionDep,
    days: int = Query(14, ge=1, le=120),
    area_id: int | None = None,
) -> VisibilityOut:
    """Vị trí trên trang kết quả của khu vực (thứ tự mặc định của kênh) cho bạn và đối thủ."""
    links = await _links(session, tenant_id)
    ids = [h for h, _, _ in links]
    stmt = select(MarketArea.id).where(MarketArea.tenant_id == tenant_id)
    if area_id:
        stmt = stmt.where(MarketArea.id == area_id)
    areas = [a for (a,) in await session.execute(stmt)]
    if not areas or not ids:
        return VisibilityOut(area_id=area_id, days=days, hotels=[])
    since = datetime.now(tz=UTC) - timedelta(days=days)
    scan_ids = [
        sid
        for (sid,) in await session.execute(
            select(MarketListScan.id).where(
                MarketListScan.area_id.in_(areas),
                MarketListScan.scanned_at >= since,
                MarketListScan.status == "completed",
            )
        )
    ]
    if not scan_ids:
        return VisibilityOut(area_id=area_id, days=days, hotels=[])
    ads: dict[int, list[int]] = defaultdict(list)
    for sid, rank in await session.execute(
        select(MarketListPrice.scan_id, MarketListPrice.rank).where(
            MarketListPrice.scan_id.in_(scan_ids), MarketListPrice.sponsored.is_(True)
        )
    ):
        ads[sid].append(rank)
    rows: dict[int, list[tuple[int, int, bool, list[str]]]] = defaultdict(list)
    for sid, hid, rank, sponsored, badges in await session.execute(
        select(
            MarketListPrice.scan_id,
            MarketListPrice.hotel_id,
            MarketListPrice.rank,
            MarketListPrice.sponsored,
            MarketListPrice.badges,
        ).where(MarketListPrice.scan_id.in_(scan_ids), MarketListPrice.hotel_id.in_(ids))
    ):
        organic = rank - sum(1 for r in ads.get(sid, []) if r < rank)
        rows[hid].append((rank, organic, bool(sponsored), list(badges or [])))
    out = []
    for h, name, role in links:
        rs = rows.get(h, [])
        q = Decimal("0.1")
        out.append(
            VisibilityHotelOut(
                hotel_id=h,
                name=name,
                role=role,
                scans=len(rs),
                avg_rank=(Decimal(sum(r[0] for r in rs)) / len(rs)).quantize(q) if rs else None,
                avg_organic_rank=(Decimal(sum(r[1] for r in rs)) / len(rs)).quantize(q)
                if rs
                else None,
                best_rank=min((r[0] for r in rs), default=None),
                sponsored_share=(Decimal(sum(1 for r in rs if r[2])) / len(rs)).quantize(
                    Decimal("0.01")
                )
                if rs
                else None,
                badges=sorted({b for r in rs for b in r[3]}),
            )
        )
    return VisibilityOut(area_id=area_id, days=days, hotels=out)
