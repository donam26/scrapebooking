"""Dựng HotelOut (khách sạn + listing Booking.com)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HotelOut, ListingOut
from app.channels.registry import BOOKING, CHANNEL_ORDER
from app.db.models import Hotel, Listing

__all__ = ["hotel_out", "hotel_outs", "tenant_channel"]


async def hotel_outs(session: AsyncSession, hotels: list[Hotel]) -> dict[int, HotelOut]:
    ids = [h.id for h in hotels]
    listings: dict[int, list[ListingOut]] = {i: [] for i in ids}
    max_seen: dict[int, tuple[int | None, datetime | None]] = {}
    if ids:
        rows = (
            await session.execute(
                select(Listing).where(Listing.hotel_id.in_(ids), Listing.status != "rejected")
            )
        ).scalars()
        for row in sorted(rows, key=lambda r: (CHANNEL_ORDER.get(r.channel, 99), r.id)):
            listings[row.hotel_id].append(ListingOut.model_validate(row))
            if row.channel == BOOKING:
                max_seen[row.hotel_id] = (row.rooms_max_seen, row.rooms_max_seen_at)
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
            rooms_total=h.rooms_total,
            rooms_total_source=h.rooms_total_source,
            rooms_total_updated_at=h.rooms_total_updated_at,
            booking_rooms_max_seen=max_seen.get(h.id, (None, None))[0],
            booking_rooms_max_seen_at=max_seen.get(h.id, (None, None))[1],
            review_score=h.review_score,
            review_count=h.review_count,
        )
        for h in hotels
    }


async def hotel_out(session: AsyncSession, hotel: Hotel) -> HotelOut:
    return (await hotel_outs(session, [hotel]))[hotel.id]


def tenant_channel() -> str:
    """Kênh dữ liệu duy nhất: Booking.com."""
    return BOOKING
