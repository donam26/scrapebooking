"""Chỉ số compset theo tenant, dùng chung cho API và insight job (spec mục 7.4).

Tính tại chỗ từ hotel_date_metrics + own_hotel_daily, không lưu bảng riêng.

Chuẩn nghề (roadmap 1.9, 1.13, 2.4, 2.7, 5.5, 7.3):
- Trung vị, **chỉ số giá niêm yết** (không gọi ARI/RPI) và **vị trí giá k/N (1 = rẻ nhất)** chỉ
  tính khi có ≥4 đối thủ có giá cùng điều kiện (quy tắc compset CoStar STR); 3 đối thủ = "mẫu
  nhỏ" (hiện mờ); dưới 3 thì không tính.
- Chỉ dùng quan sát ≤48 giờ (so với quan sát mới nhất của đêm): listing tạm dừng/bị chặn nhiều
  ngày không góp giá cũ vào trung vị.
- Đêm bị hạn chế (lịch không cho nhận phòng, hoặc chỉ bán từ N>1 đêm) đếm riêng, không tính là
  hết phòng và không đem giá so với giá 1 đêm.
- Compset riêng cho từng khách sạn của bạn (`tenant_hotels.compset_of`); chỉ compset chính
  (`tier = primary`) vào trung vị.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import median
from app.db.models import HotelDateMetric, OwnHotelDaily, TenantHotel


class PriceBasis(StrEnum):
    """Giá đem so (cùng điều kiện): rẻ nhất mọi gói; rẻ nhất trong các gói huỷ miễn phí (gần BAR
    nhất); có bữa sáng; chỉ phòng. Đối thủ bán gói không hoàn huỷ rẻ hơn 10–20%, giá gồm bữa sáng
    phổ biến ở Việt Nam: so lệch điều kiện làm trung vị sai."""

    ANY = "any"
    REFUNDABLE = "refundable"
    BREAKFAST = "breakfast"
    ROOM_ONLY = "room_only"


def metric_price(m: HotelDateMetric, basis: PriceBasis) -> Decimal | None:
    if basis == PriceBasis.REFUNDABLE:
        return m.min_refundable_price
    if basis == PriceBasis.BREAKFAST:
        return m.min_breakfast_price
    if basis == PriceBasis.ROOM_ONLY:
        return m.min_room_only_price
    return m.min_price


MIN_SAMPLE = 4  # CoStar STR: compset ≥4 đối thủ
SMALL_SAMPLE = 3  # 3 đối thủ: hiện mờ "mẫu nhỏ"
STALE_AFTER = timedelta(hours=48)
LOW_STOCK = 3

Sample = Literal["ok", "small", "insufficient"]


def sample_level(n: int) -> Sample:
    if n >= MIN_SAMPLE:
        return "ok"
    if n >= SMALL_SAMPLE:
        return "small"
    return "insufficient"


def is_restricted(m: HotelDateMetric) -> bool:
    return m.availability_status == "restricted" or (
        m.availability_status == "available" and (m.min_stay or 1) > 1
    )


@dataclass(frozen=True)
class CompsetDay:
    stay_date: date
    competitors_observed: int
    competitors_sold_out: int
    sold_out_share: Decimal | None
    min_price: Decimal | None
    median_price: Decimal | None
    currency: str | None
    own_min_price: Decimal | None
    own_status: str | None
    own_occupancy_pct: Decimal | None
    own_rooms_available: int | None
    price_index: Decimal | None  # chỉ số giá niêm yết = own_min_price / median_price * 100
    # Vị trí giá của khách sạn bạn trong các khách sạn có giá đêm đó (1 = rẻ nhất, bằng giá thì
    # cùng hạng) và số khách sạn có giá (gồm bạn). Không có giá của bạn thì None.
    own_rank: int | None
    priced_hotels: int
    # Cỡ mẫu và chất lượng (1.9, 1.13, 2.7)
    competitors_total: int = 0  # đối thủ compset chính trong watchlist (N)
    competitors_priced: int = 0  # đối thủ có giá cùng điều kiện (n)
    competitors_restricted: int = 0
    competitors_low: int = 0  # còn ≤3 phòng (số chính xác)
    competitors_stale: int = 0  # có quan sát nhưng cũ hơn 48h: không tính
    sample: Sample = "insufficient"
    own_hotel_id: int | None = None
    own_min_stay: int | None = None


def price_rank(own_price: Decimal | None, competitor_prices: list[Decimal]) -> int | None:
    """Vị trí giá của bạn: 1 + số đối thủ rẻ hơn hẳn (đối thủ bằng giá không đẩy hạng xuống)."""
    if own_price is None:
        return None
    return 1 + sum(1 for p in competitor_prices if p < own_price)


@dataclass(frozen=True)
class Watchlist:
    own: list[int]  # khách sạn của bạn, theo thứ tự thêm (đầu tiên = mặc định)
    competitors: list[int]  # compset chính của khách sạn đang xem
    secondary: list[int]  # compset phụ


async def load_compset(
    session: AsyncSession, tenant_id: int, own_hotel_id: int | None = None
) -> Watchlist:
    rows = (
        await session.execute(
            select(TenantHotel.hotel_id, TenantHotel.role, TenantHotel.compset_of, TenantHotel.tier)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
            .order_by(TenantHotel.added_at, TenantHotel.hotel_id)
        )
    ).all()
    own = [r[0] for r in rows if r[1] == "self"]
    focus = own_hotel_id if own_hotel_id in own else (own[0] if own else None)
    mine = [
        r for r in rows if r[1] == "competitor" and (r[2] is None or focus is None or r[2] == focus)
    ]
    return Watchlist(
        own,
        [r[0] for r in mine if (r[3] or "primary") == "primary"],
        [r[0] for r in mine if (r[3] or "primary") != "primary"],
    )


async def load_watchlist(session: AsyncSession, tenant_id: int) -> tuple[list[int], list[int]]:
    """(hotel_ids của khách hàng, hotel_ids đối thủ compset chính) đang active."""
    w = await load_compset(session, tenant_id)
    return w.own, w.competitors


def compset_day(
    d: date,
    own: HotelDateMetric | None,
    comps: list[HotelDateMetric],
    competitors_total: int,
    basis: PriceBasis,
    now: datetime,
    own_daily: OwnHotelDaily | None = None,
    own_hotel_id: int | None = None,
) -> CompsetDay:
    """Hàm thuần cho một đêm (dễ test): `comps` = metric của đối thủ compset chính trên một kênh.

    Cũ = quan sát cũ hơn 48 giờ so với quan sát mới nhất của đêm đó trong compset (không quá
    `now`): listing tạm dừng/bị chặn nhiều ngày bị loại khỏi trung vị. Khi cả hệ thống mất dữ liệu,
    compset vẫn hiện số cuối cùng — độ mới của dữ liệu báo riêng ở /data-status và `DateCell.stale`.
    """
    stamps = [m.last_observed_at for m in comps] + ([own.last_observed_at] if own else [])
    ref = min(now, max(stamps)) if stamps else now
    fresh = [m for m in comps if ref - m.last_observed_at <= STALE_AFTER]
    stale = len(comps) - len(fresh)
    observed = [
        m for m in fresh if m.availability_status in ("available", "sold_out", "restricted")
    ]
    sold_out = [m for m in observed if m.availability_status == "sold_out"]
    restricted = [m for m in observed if is_restricted(m)]
    low = [
        m
        for m in observed
        if m.availability_status == "available"
        and m.exact_rooms_left is not None
        and m.exact_rooms_left <= LOW_STOCK
    ]
    prices = [
        p
        for m in observed
        if m.availability_status == "available"
        and not is_restricted(m)
        and (p := metric_price(m, basis)) is not None
    ]
    currency = next((m.currency for m in observed if m.currency), None)
    own_fresh = own is not None and ref - own.last_observed_at <= STALE_AFTER
    own_price = (
        metric_price(own, basis)
        if own is not None
        and own_fresh
        and own.availability_status == "available"
        and not is_restricted(own)
        else None
    )
    sample = sample_level(len(prices))
    med = median(prices) if sample != "insufficient" else None
    price_index = (
        (own_price / med * 100).quantize(Decimal("0.1"))
        if own_price is not None and med not in (None, Decimal(0))
        else None
    )
    return CompsetDay(
        stay_date=d,
        competitors_observed=len(observed),
        competitors_sold_out=len(sold_out),
        sold_out_share=(
            (Decimal(len(sold_out)) / Decimal(len(observed))).quantize(Decimal("0.01"))
            if observed
            else None
        ),
        min_price=min(prices) if prices else None,
        median_price=med,
        currency=currency,
        own_min_price=own_price,
        own_status=own.availability_status if own is not None and own_fresh else None,
        own_occupancy_pct=own_daily.occupancy_pct if own_daily else None,
        own_rooms_available=own_daily.rooms_available if own_daily else None,
        price_index=price_index,
        own_rank=price_rank(own_price, prices) if sample != "insufficient" else None,
        priced_hotels=len(prices) + (1 if own_price is not None else 0),
        competitors_total=competitors_total,
        competitors_priced=len(prices),
        competitors_restricted=len(restricted),
        competitors_low=len(low),
        competitors_stale=stale,
        sample=sample,
        own_hotel_id=own_hotel_id,
        own_min_stay=(own.min_stay or 1) if own is not None and own_fresh else None,
    )


async def compset_by_day(
    session: AsyncSession,
    tenant_id: int,
    start: date,
    end: date,
    basis: PriceBasis = PriceBasis.ANY,
    channel: str = "booking",
    own_hotel_id: int | None = None,
    now: datetime | None = None,
) -> list[CompsetDay]:
    """Compset của một kênh (D10) cho một khách sạn của bạn (mặc định khách sạn đầu tiên): giá
    giữa các kênh khác cơ sở, không trộn vào một trung vị."""
    now = now or datetime.now(tz=UTC)
    w = await load_compset(session, tenant_id, own_hotel_id)
    own_id = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    ids = ([own_id] if own_id else []) + w.competitors
    if not ids:
        return []
    metrics = (
        (
            await session.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id.in_(ids),
                    HotelDateMetric.channel == channel,
                    HotelDateMetric.stay_date >= start,
                    HotelDateMetric.stay_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    own_daily: dict[date, OwnHotelDaily] = {}
    if own_id:
        rows = (
            (
                await session.execute(
                    select(OwnHotelDaily).where(
                        OwnHotelDaily.tenant_id == tenant_id,
                        OwnHotelDaily.hotel_id == own_id,
                        OwnHotelDaily.stay_date >= start,
                        OwnHotelDaily.stay_date <= end,
                    )
                )
            )
            .scalars()
            .all()
        )
        own_daily = {r.stay_date: r for r in rows}

    by_date: dict[date, list[HotelDateMetric]] = {}
    for m in metrics:
        by_date.setdefault(m.stay_date, []).append(m)
    comp_set = set(w.competitors)
    out: list[CompsetDay] = []
    d = start
    while d <= end:
        rows_d = by_date.get(d, [])
        own = next((m for m in rows_d if m.hotel_id == own_id), None)
        comps = [m for m in rows_d if m.hotel_id in comp_set]
        out.append(
            compset_day(d, own, comps, len(w.competitors), basis, now, own_daily.get(d), own_id)
        )
        d += timedelta(days=1)
    return out


REVIEW_EVERY = timedelta(days=183)  # Lighthouse: rà soát compset ít nhất 2 lần/năm
DOMINANT_SHARE = Decimal("0.5")  # CoStar STR: không khách sạn nào quá 50% số phòng compset


@dataclass(frozen=True)
class CompsetReview:
    warnings: list[str]
    rooms_known: int
    dominant_hotel_id: int | None = None
    dominant_share: Decimal | None = None


def review_compset(
    competitors: list[int],
    rooms_total: dict[int, int | None],
    last_change_at: datetime | None,
    now: datetime,
) -> CompsetReview:
    """Cảnh báo compset (7.3): too_few (<4 đối thủ chính), rooms_unknown (thiếu tổng số phòng nên
    chưa kiểm được quy tắc 50%), dominant_hotel (một khách sạn >50% số phòng), review_due (không
    đổi compset quá 6 tháng)."""
    warnings: list[str] = []
    if len(competitors) < MIN_SAMPLE:
        warnings.append("too_few")
    known = {h: r for h in competitors if (r := rooms_total.get(h))}
    dominant: tuple[int, Decimal] | None = None
    if len(known) < len(competitors):
        warnings.append("rooms_unknown")
    if known:
        total = sum(known.values())
        hid, rooms = max(known.items(), key=lambda kv: kv[1])
        share = (Decimal(rooms) / Decimal(total)).quantize(Decimal("0.01"))
        if len(known) == len(competitors) and share > DOMINANT_SHARE:
            warnings.append("dominant_hotel")
            dominant = (hid, share)
    if last_change_at is not None and now - last_change_at > REVIEW_EVERY:
        warnings.append("review_due")
    return CompsetReview(
        warnings,
        len(known),
        dominant[0] if dominant else None,
        dominant[1] if dominant else None,
    )
