"""Chỉ số compset theo tenant, dùng chung cho API và insight job (spec mục 7.4).

Tính tại chỗ từ hotel_date_metrics + own_hotel_daily, không lưu bảng riêng.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import median
from app.db.models import HotelDateMetric, OwnHotelDaily, TenantHotel

# Giá giữ lại từ lần dùng được cuối (probe sau đó bị chặn/lỗi) còn đem so tới ngưỡng này, tính từ
# quan sát mới nhất của đêm đó; lâu hơn thì đối thủ coi như không quan sát được (đối thủ paused/
# broken không đóng góp giá hai tuần tuổi vào trung vị).
STALE_PRICE_MAX_AGE = timedelta(hours=24)


class PriceBasis(StrEnum):
    """Giá đem so: rẻ nhất mọi gói, hoặc rẻ nhất trong các gói có huỷ miễn phí. Đối thủ bán gói
    không hoàn huỷ rẻ hơn 15–20% làm trung vị lệch; so cùng điều kiện hoàn huỷ thì công bằng hơn."""

    ANY = "any"
    REFUNDABLE = "refundable"


def metric_price(m: HotelDateMetric, basis: PriceBasis) -> Decimal | None:
    return m.min_refundable_price if basis == PriceBasis.REFUNDABLE else m.min_price


def price_is_fresh(m: HotelDateMetric, as_of: datetime | None) -> bool:
    """Giá của metric còn dùng được: lần quan sát mới nhất dùng được (`stale_since` None), hoặc giá
    giữ lại chưa cũ quá `STALE_PRICE_MAX_AGE` so với `as_of` (quan sát mới nhất của đêm)."""
    if m.stale_since is None:
        return True
    return (as_of or m.last_observed_at) - m.stale_since <= STALE_PRICE_MAX_AGE


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
    price_index: Decimal | None  # own_min_price / median_price * 100
    # Hạng giá của khách sạn bạn trong các khách sạn có giá đêm đó (1 = rẻ nhất, bằng giá thì cùng
    # hạng) và số khách sạn có giá (gồm bạn). Không có giá của bạn thì hạng là None.
    own_rank: int | None
    priced_hotels: int
    # Đối thủ có giá nhưng khác tiền tệ với `currency` (của bạn, hoặc đa số): bị loại khỏi trung vị.
    dropped_currency: int = 0


def price_rank(own_price: Decimal | None, competitor_prices: list[Decimal]) -> int | None:
    """Hạng giá của bạn: 1 + số đối thủ rẻ hơn hẳn (đối thủ bằng giá không đẩy hạng xuống)."""
    if own_price is None:
        return None
    return 1 + sum(1 for p in competitor_prices if p < own_price)


async def load_watchlist(session: AsyncSession, tenant_id: int) -> tuple[list[int], list[int]]:
    """(hotel_ids của khách hàng, hotel_ids đối thủ) đang active."""
    rows = (
        await session.execute(
            select(TenantHotel.hotel_id, TenantHotel.role).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True)
            )
        )
    ).all()
    own = [r[0] for r in rows if r[1] == "self"]
    comp = [r[0] for r in rows if r[1] == "competitor"]
    return own, comp


def _observed(m: HotelDateMetric, as_of: datetime | None) -> bool:
    """Đối thủ "quan sát được" đêm đó: trạng thái dùng được, hoặc probe lỗi nhưng giá giữ lại còn
    mới (lần dùng được cuối là còn phòng)."""
    if m.availability_status != "unknown":
        return True
    return m.min_price is not None and price_is_fresh(m, as_of)


def _reference_currency(owns: list[HotelDateMetric], comps: list[HotelDateMetric]) -> str | None:
    """Tiền tệ đem so: của khách sạn bạn (khách sạn self nhỏ nhất trước); không có thì tiền tệ
    phổ biến nhất trong đối thủ có giá (hoà → mã nhỏ hơn)."""
    own = next((m.currency for m in owns if m.currency), None)
    if own is not None:
        return own
    counts = Counter(m.currency for m in comps if m.currency and m.min_price is not None)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


async def compset_by_day(
    session: AsyncSession,
    tenant_id: int,
    start: date,
    end: date,
    basis: PriceBasis = PriceBasis.ANY,
    channel: str = "booking",
) -> list[CompsetDay]:
    """Compset của một kênh (D10): giá giữa các kênh khác cơ sở, không trộn vào một trung vị.

    Chỉ so giá cùng tiền tệ (`dropped_currency` đếm đối thủ bị loại); giá giữ lại sau probe lỗi
    dùng tới 24h. Nhiều khách sạn `self`: trạng thái/PMS lấy theo khách sạn self nhỏ nhất (ổn
    định), giá của bạn là giá thấp nhất trong các khách sạn self."""
    own_ids, comp_ids = await load_watchlist(session, tenant_id)
    all_ids = own_ids + comp_ids
    if not all_ids:
        return []
    primary_own = min(own_ids) if own_ids else None
    metrics = (
        (
            await session.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id.in_(all_ids),
                    HotelDateMetric.channel == channel,
                    HotelDateMetric.stay_date >= start,
                    HotelDateMetric.stay_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    own_daily: dict[tuple[int, date], OwnHotelDaily] = {}
    if own_ids:
        rows = (
            (
                await session.execute(
                    select(OwnHotelDaily).where(
                        OwnHotelDaily.tenant_id == tenant_id,
                        OwnHotelDaily.hotel_id.in_(own_ids),
                        OwnHotelDaily.stay_date >= start,
                        OwnHotelDaily.stay_date <= end,
                    )
                )
            )
            .scalars()
            .all()
        )
        own_daily = {(r.hotel_id, r.stay_date): r for r in rows}

    by_date: dict[date, list[HotelDateMetric]] = {}
    for m in metrics:
        by_date.setdefault(m.stay_date, []).append(m)

    out: list[CompsetDay] = []
    d = start
    while d <= end:
        rows_d = by_date.get(d, [])
        newest = max((m.last_observed_at for m in rows_d), default=None)
        comps = [m for m in rows_d if m.hotel_id in comp_ids and _observed(m, newest)]
        owns = sorted((m for m in rows_d if m.hotel_id in own_ids), key=lambda m: m.hotel_id)
        sold_out = [m for m in comps if m.availability_status == "sold_out"]
        currency = _reference_currency(owns, comps)
        priced = [(m, p) for m in comps if (p := metric_price(m, basis)) is not None]
        prices = [p for m, p in priced if currency is None or m.currency == currency]
        own_price = min(
            (
                p
                for m in owns
                if price_is_fresh(m, newest)
                and (currency is None or m.currency == currency)
                and (p := metric_price(m, basis)) is not None
            ),
            default=None,
        )
        own_primary = next((m for m in owns if m.hotel_id == primary_own), None)
        own_status = own_primary.availability_status if own_primary else None
        med = median(prices)
        own_row = own_daily.get((primary_own, d)) if primary_own is not None else None
        price_index = (
            (own_price / med * 100).quantize(Decimal("0.1"))
            if own_price is not None and med not in (None, Decimal(0))
            else None
        )
        out.append(
            CompsetDay(
                stay_date=d,
                competitors_observed=len(comps),
                competitors_sold_out=len(sold_out),
                sold_out_share=(
                    (Decimal(len(sold_out)) / Decimal(len(comps))).quantize(Decimal("0.01"))
                    if comps
                    else None
                ),
                min_price=min(prices) if prices else None,
                median_price=med,
                currency=currency,
                own_min_price=own_price,
                own_status=own_status,
                own_occupancy_pct=own_row.occupancy_pct if own_row else None,
                own_rooms_available=own_row.rooms_available if own_row else None,
                price_index=price_index,
                own_rank=price_rank(own_price, prices),
                priced_hotels=len(prices) + (1 if own_price is not None else 0),
                dropped_currency=len(priced) - len(prices),
            )
        )
        d = d.fromordinal(d.toordinal() + 1)
    return out
