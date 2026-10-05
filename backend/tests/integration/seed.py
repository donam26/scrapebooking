"""Dựng dữ liệu đa kênh cho test tích hợp: khách sạn (property) + listing mỗi kênh."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Listing, ScanRun


def listing_url(channel: str, key: str) -> str:
    if channel == "booking":
        return f"https://www.booking.com/hotel/{key}.html"
    return f"https://{channel}.example/{key}"


async def add_listing(
    db: AsyncSession,
    hotel_id: int,
    channel: str,
    key: str,
    *,
    status: str = "active",
    name: str | None = None,
) -> Listing:
    listing = Listing(
        hotel_id=hotel_id,
        channel=channel,
        listing_key=key,
        url=listing_url(channel, key),
        name=name,
        status=status,
    )
    db.add(listing)
    await db.flush()
    return listing


async def add_hotel(
    db: AsyncSession,
    slug: str,
    *,
    name: str | None = None,
    channels: tuple[str, ...] = ("booking",),
    status: str = "active",
    country_code: str = "vn",
) -> Hotel:
    """Khách sạn có listing `slug` trên mỗi kênh trong `channels` (cùng trạng thái `status`)."""
    hotel = Hotel(name=name, country_code=country_code)
    db.add(hotel)
    await db.flush()
    for channel in channels:
        await add_listing(db, hotel.id, channel, slug, status=status)
    return hotel


def scan_run(
    trigger_key: str,
    at: datetime,
    *,
    channel: str = "booking",
    status: str = "completed",
    finished_at: datetime | None = None,
) -> ScanRun:
    return ScanRun(
        trigger_key=trigger_key,
        channel=channel,
        scheduled_at=at,
        started_at=at,
        finished_at=finished_at,
        status=status,
    )
