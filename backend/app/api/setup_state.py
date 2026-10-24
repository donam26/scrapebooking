"""Thẻ "Thiết lập 5 bước" (UX Phase 3, C1) và cảnh báo nhóm đối thủ lệch giá (Q4).

Bước: (1) khách sạn của bạn, (2) ≥4 đối thủ chính, (3) đã lưu chiến lược giá, (4) có người nhận
cảnh báo đang bật, (5) đã nhập PMS (tuỳ chọn). Trạng thái tính từ dữ liệu, chỉ "Ẩn" được lưu
(`tenants.setup_state.dismissed_at`).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import MIN_SAMPLE, load_compset
from app.analytics.compset_balance import CompsetBalance, load_compset_balance
from app.api.schemas import CompsetBalanceOut, SetupOut
from app.db.models import Hotel, NotificationSubscription, OwnHotelDaily, PmsImport, Tenant
from app.market.models import OtbSnapshot, PriceStrategy
from app.market.pace_report import tenant_today


def balance_out(b: CompsetBalance, stars: Decimal | None = None) -> CompsetBalanceOut | None:
    if b.ratio is None or b.own_price is None or b.comp_price is None:
        return None
    return CompsetBalanceOut(
        nights=b.nights,
        own_price=b.own_price,
        comp_price=b.comp_price,
        ratio=b.ratio,
        pricier=b.pricier,
        own_stars=stars,
    )


async def own_balance(
    session: AsyncSession, tenant: Tenant, own_hotel_id: int | None
) -> CompsetBalanceOut | None:
    """Giá giữa nhóm đối thủ so với giá bạn, 14 đêm tới; None khi chưa có khách sạn của bạn."""
    if own_hotel_id is None:
        return None
    b = await load_compset_balance(session, tenant.id, tenant_today(tenant), own_hotel_id)
    stars = (
        await session.execute(select(Hotel.star_rating).where(Hotel.id == own_hotel_id))
    ).scalar_one_or_none()
    return balance_out(b, stars)


def _dismissed_at(state: dict[str, object] | None) -> datetime | None:
    raw = (state or {}).get("dismissed_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


async def build_setup(session: AsyncSession, tenant: Tenant) -> SetupOut:
    w = await load_compset(session, tenant.id)
    own = w.own[0] if w.own else None

    async def has(stmt: object) -> bool:
        return bool((await session.execute(select(stmt))).scalar())  # type: ignore[call-overload]

    strategy = await has(exists().where(PriceStrategy.tenant_id == tenant.id))
    alerts = await has(
        exists().where(
            NotificationSubscription.tenant_id == tenant.id,
            NotificationSubscription.active.is_(True),
        )
    )
    pms = (
        await has(
            exists().where(
                PmsImport.tenant_id == tenant.id,
                PmsImport.ok_count > 0,
            )
        )
        or await has(exists().where(OwnHotelDaily.tenant_id == tenant.id))
        or await has(exists().where(OtbSnapshot.tenant_id == tenant.id))
    )
    done = own is not None and len(w.competitors) >= MIN_SAMPLE and strategy and alerts
    return SetupOut(
        own_hotel_id=own,
        own_hotel=own is not None,
        competitors=len(w.competitors),
        competitors_needed=MIN_SAMPLE,
        strategy=strategy,
        alerts=alerts,
        pms=pms,
        done=done,
        dismissed_at=_dismissed_at(tenant.setup_state),
        balance=await own_balance(session, tenant, own),
    )
