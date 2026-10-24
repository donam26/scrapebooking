"""Nhóm đối thủ có cân về giá không (UX Phase 3, Q4): so giá giữa của nhóm đối thủ với giá của
khách sạn bạn trên các đêm sắp tới. Nhóm đắt hơn bạn ≥1,6 lần (VD Rex ~2 lần) thì giá giữa không
còn là mốc so hợp lý: gợi ý thêm vài khách sạn cùng tầm giá.

Chỉ dùng đêm có cả giá của bạn và giá giữa đủ mẫu (≥3 đối thủ có giá). Giá niêm yết Booking.com.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import CompsetDay, compset_by_day
from app.analytics.rules import median

BALANCE_NIGHTS = 14
PRICIER_RATIO = Decimal("1.6")
MIN_NIGHTS = 3


@dataclass(frozen=True)
class CompsetBalance:
    nights: int  # số đêm đủ dữ liệu để so
    own_price: Decimal | None  # giá giữa các đêm của bạn
    comp_price: Decimal | None  # giá giữa các đêm của giá giữa đối thủ
    ratio: Decimal | None  # trung vị (giá giữa đối thủ / giá bạn) theo đêm

    @property
    def pricier(self) -> bool:
        return self.ratio is not None and self.ratio >= PRICIER_RATIO


def _mid(values: list[Decimal]) -> Decimal:
    m = median(values)
    assert m is not None  # danh sách không rỗng
    return m


def compset_balance(days: Sequence[CompsetDay]) -> CompsetBalance:
    pairs: list[tuple[Decimal, Decimal]] = [
        (d.own_min_price, d.median_price)
        for d in days
        if d.own_min_price and d.median_price and d.sample != "insufficient"
    ]
    if len(pairs) < MIN_NIGHTS:
        return CompsetBalance(len(pairs), None, None, None)
    return CompsetBalance(
        nights=len(pairs),
        own_price=_mid([o for o, _ in pairs]).quantize(Decimal(1)),
        comp_price=_mid([m for _, m in pairs]).quantize(Decimal(1)),
        ratio=_mid([m / o for o, m in pairs]).quantize(Decimal("0.01")),
    )


async def load_compset_balance(
    session: AsyncSession,
    tenant_id: int,
    today: date,
    own_hotel_id: int | None = None,
    now: datetime | None = None,
) -> CompsetBalance:
    days = await compset_by_day(
        session,
        tenant_id,
        today,
        today + timedelta(days=BALANCE_NIGHTS - 1),
        own_hotel_id=own_hotel_id,
        now=now,
    )
    return compset_balance(days)
