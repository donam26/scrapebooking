"""Dựng HotelOut (khách sạn + listing Booking.com + gợi ý số phòng đo trên Booking)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HotelOut, ListingOut, RoomsSuggestionOut
from app.channels.registry import BOOKING, CHANNEL_ORDER
from app.db.models import Hotel, Listing, RoomType
from app.domain.capacity import rooms_suggestion, sells_beds

__all__ = ["hotel_out", "hotel_outs", "tenant_channel"]


async def _bed_hotels(session: AsyncSession, hotel_ids: list[int]) -> set[int]:
    """Khách sạn mà Booking bán giường dorm (theo tên loại phòng đã thấy)."""
    if not hotel_ids:
        return set()
    names: dict[int, list[str]] = {}
    for hid, name in await session.execute(
        select(RoomType.hotel_id, RoomType.name).where(
            RoomType.hotel_id.in_(hotel_ids), RoomType.channel == BOOKING
        )
    ):
        names.setdefault(hid, []).append(name)
    return {hid for hid, n in names.items() if sells_beds(n)}


def _suggestion(listing: Listing | None, beds: set[int]) -> RoomsSuggestionOut | None:
    if listing is None:
        return None
    s = rooms_suggestion(
        listing.capacity_max,
        listing.capacity_capped,
        listing.rooms_max_seen,
        measured=listing.capacity_checked_at is not None,
        includes_beds=listing.hotel_id in beds,
    )
    if s is None:
        return None
    return RoomsSuggestionOut(
        rooms=s.rooms,
        lower_bound=s.lower_bound,
        capped=s.capped,
        includes_beds=s.includes_beds,
        confirmable=s.confirmable,
        measured_at=listing.capacity_checked_at,
        source_url=listing.url,
    )


async def hotel_outs(session: AsyncSession, hotels: list[Hotel]) -> dict[int, HotelOut]:
    ids = [h.id for h in hotels]
    listings: dict[int, list[ListingOut]] = {i: [] for i in ids}
    booking: dict[int, Listing] = {}
    if ids:
        rows = (
            await session.execute(
                select(Listing).where(Listing.hotel_id.in_(ids), Listing.status != "rejected")
            )
        ).scalars()
        for row in sorted(rows, key=lambda r: (CHANNEL_ORDER.get(r.channel, 99), r.id)):
            listings[row.hotel_id].append(ListingOut.model_validate(row))
            if row.channel == BOOKING:
                booking[row.hotel_id] = row
    measured = [hid for hid, li in booking.items() if li.capacity_checked_at is not None]
    beds = await _bed_hotels(session, measured)
    out: dict[int, HotelOut] = {}
    for h in hotels:
        b = booking.get(h.id)
        out[h.id] = HotelOut(
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
            booking_rooms_max_seen=b.rooms_max_seen if b else None,
            booking_rooms_max_seen_at=b.rooms_max_seen_at if b else None,
            rooms_suggestion=_suggestion(b, beds),
            review_score=h.review_score,
            review_count=h.review_count,
        )
    return out


async def hotel_out(session: AsyncSession, hotel: Hotel) -> HotelOut:
    return (await hotel_outs(session, [hotel]))[hotel.id]


def tenant_channel() -> str:
    """Kênh dữ liệu duy nhất: Booking.com."""
    return BOOKING
