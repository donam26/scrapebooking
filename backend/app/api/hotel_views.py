"""Dựng HotelOut (khách sạn + listing từng kênh) và chọn kênh đang xem của tenant."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HotelOut, ListingOut
from app.channels.registry import CHANNEL_ORDER, sort_channels
from app.db.models import Hotel, Listing, Tenant, TenantHotel

__all__ = ["hotel_out", "hotel_outs", "sort_channels", "tenant_channel", "tenant_channels"]


def listing_out(row: Listing, *, operator: bool = False) -> ListingOut:
    """`last_error` chứa lỗi kỹ thuật (proxy, mã lỗi kênh): tenant chỉ thấy mã ngắn, operator
    thấy nguyên văn."""
    out = ListingOut.model_validate(row)
    if not operator and out.last_error:
        out.last_error = short_listing_error(out.last_error)
    return out


def short_listing_error(error: str) -> str:
    head = error.split(":", 1)[0].strip().lower()
    if head.startswith("duplicate"):
        return "duplicate"
    if "not_found" in head or "404" in head:
        return "not_found"
    if "block" in head or "challenge" in head or "token" in head:
        return "blocked"
    if "identity" in head or "mismatch" in head:
        return "identity_mismatch"
    return "error"


async def hotel_outs(
    session: AsyncSession, hotels: list[Hotel], *, operator: bool = False
) -> dict[int, HotelOut]:
    ids = [h.id for h in hotels]
    listings: dict[int, list[ListingOut]] = {i: [] for i in ids}
    if ids:
        rows = (
            await session.execute(
                select(Listing).where(Listing.hotel_id.in_(ids), Listing.status != "rejected")
            )
        ).scalars()
        for row in sorted(rows, key=lambda r: (CHANNEL_ORDER.get(r.channel, 99), r.id)):
            listings[row.hotel_id].append(listing_out(row, operator=operator))
    return {
        h.id: HotelOut(
            id=h.id,
            name=h.name,
            city=h.city,
            country_code=h.country_code,
            star_rating=h.star_rating,
            address=h.address,
            lat=h.lat,
            lng=h.lng,
            listings=listings[h.id],
        )
        for h in hotels
    }


async def hotel_out(session: AsyncSession, hotel: Hotel, *, operator: bool = False) -> HotelOut:
    return (await hotel_outs(session, [hotel], operator=operator))[hotel.id]


async def tenant_channels(session: AsyncSession, tenant_id: int) -> list[str]:
    """Kênh có listing đang quét (active) trong watchlist đang theo dõi của tenant."""
    rows = await session.execute(
        select(Listing.channel)
        .join(TenantHotel, TenantHotel.hotel_id == Listing.hotel_id)
        .where(
            TenantHotel.tenant_id == tenant_id,
            TenantHotel.active.is_(True),
            Listing.status == "active",
        )
        .distinct()
    )
    return sort_channels(r[0] for r in rows)


async def tenant_channel(session: AsyncSession, tenant_id: int, channel: str | None) -> str:
    """Kênh đang xem: tham số `channel` nếu có, không thì kênh tham chiếu của tenant."""
    if channel:
        if channel not in CHANNEL_ORDER:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown channel {channel}")
        return channel
    tenant = await session.get(Tenant, tenant_id)
    return tenant.reference_channel if tenant else "booking"
