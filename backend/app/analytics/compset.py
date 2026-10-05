"""Chỉ số compset theo tenant, dùng chung cho API và insight job (spec mục 7.4).

Tính tại chỗ từ hotel_date_metrics + own_hotel_daily, không lưu bảng riêng.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import median
from app.db.models import HotelDateMetric, OwnHotelDaily, TenantHotel


class PriceBasis(StrEnum):
    """Giá đem so: rẻ nhất mọi gói, hoặc rẻ nhất trong các gói có huỷ miễn phí. Đối thủ bán gói
    không hoàn huỷ rẻ hơn 15–20% làm trung vị lệch; so cùng điều kiện hoàn huỷ thì công bằng hơn."""

    ANY = "any"
    REFUNDABLE = "refundable"


def metric_price(m: HotelDateMetric, basis: PriceBasis) -> Decimal | None:
    return m.min_refundable_price if basis == PriceBasis.REFUNDABLE else m.min_price


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


async def compset_by_day(
    session: AsyncSession,
    tenant_id: int,
    start: date,
    end: date,
    basis: PriceBasis = PriceBasis.ANY,
    channel: str = "booking",
) -> list[CompsetDay]:
    """Compset của một kênh (D10): giá giữa các kênh khác cơ sở, không trộn vào một trung vị."""
    own_ids, comp_ids = await load_watchlist(session, tenant_id)
    all_ids = own_ids + comp_ids
    if not all_ids:
        return []
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
    own_daily = {}
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
        own_daily = {r.stay_date: r for r in rows}

    by_date: dict[date, list[HotelDateMetric]] = {}
    for m in metrics:
        by_date.setdefault(m.stay_date, []).append(m)

    out: list[CompsetDay] = []
    d = start
    while d <= end:
        rows_d = by_date.get(d, [])
        comps = [m for m in rows_d if m.hotel_id in comp_ids and m.availability_status != "unknown"]
        owns = [m for m in rows_d if m.hotel_id in own_ids]
        sold_out = [m for m in comps if m.availability_status == "sold_out"]
        prices = [p for m in comps if (p := metric_price(m, basis)) is not None]
        currency = next((m.currency for m in comps if m.currency), None)
        own_price = min(
            (p for m in owns if (p := metric_price(m, basis)) is not None), default=None
        )
        own_status = owns[0].availability_status if owns else None
        med = median(prices)
        own_row = own_daily.get(d)
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
            )
        )
        d = d.fromordinal(d.toordinal() + 1)
    return out
