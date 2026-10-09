"""Job vòng đời listing: verify_listing — URL Booking.com người dùng dán → khách sạn nào (tên, id,
toạ độ) → active | broken."""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import ChannelCollector
from app.db.models import Hotel, Listing
from app.domain.models import ListingRef
from app.logging import get_logger

log = get_logger(__name__)


class ListingRetry(RuntimeError):
    """Bị chặn khi verify: để arq thử lại sau."""


@dataclass
class ListingJobDeps:
    session_factory: async_sessionmaker[AsyncSession]
    collector: ChannelCollector
    clock: Clock
    channel: str


async def run_verify_listing(deps: ListingJobDeps, listing_id: int, final_attempt: bool) -> str:
    async with deps.session_factory() as s:
        row = (
            await s.execute(
                select(Listing, Hotel)
                .join(Hotel, Hotel.id == Listing.hotel_id)
                .where(Listing.id == listing_id)
            )
        ).first()
        if row is None:
            return "missing"
        listing, hotel = row
        ref = ListingRef(
            hotel_id=hotel.id,
            channel=listing.channel,
            listing_key=listing.listing_key,
            url=listing.url,
            country_code=hotel.country_code,
            external_id=listing.external_id,
        )
    try:
        identity = await deps.collector.verify(ref)
    except ListingNotFound:
        await _set_status(deps, listing_id, "broken", "not_found")
        return "broken"
    except ListingBlocked as exc:
        if not final_attempt:
            raise ListingRetry(str(exc)) from exc
        log.warning("listing_verify_blocked", listing_id=listing_id, error=str(exc))
        await _set_status(deps, listing_id, None, "blocked")
        return "blocked"
    except Exception as exc:  # noqa: BLE001 — mạng chập chờn, timeout proxy: thử lại như bị chặn
        log.warning("listing_verify_error", listing_id=listing_id, error=repr(exc))
        if not final_attempt:
            raise ListingRetry(repr(exc)) from exc
        await _set_status(deps, listing_id, None, f"error: {type(exc).__name__}")
        return "error"
    other_hotel = await _hotel_with_external_id(deps, listing_id, identity.external_id)
    if other_hotel is not None:
        # Hai URL khác nhau cùng trỏ một khách sạn (VD slug Booking đổi, có redirect): không
        # quét trùng, báo người dùng gắn vào khách sạn đã có.
        await _set_status(
            deps,
            listing_id,
            "broken",
            f"duplicate: same hotel #{other_hotel} on this channel (id {identity.external_id})",
        )
        return "duplicate"
    now = deps.clock.now()
    async with deps.session_factory() as s:
        listing = (await s.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()
        hotel = (await s.execute(select(Hotel).where(Hotel.id == listing.hotel_id))).scalar_one()
        listing.status = "active" if listing.status in ("unverified", "broken") else listing.status
        listing.external_id = identity.external_id or listing.external_id
        listing.name = (identity.name or listing.name or "")[:300] or None
        listing.verified_at = now
        listing.last_error = None
        # Khách sạn (property) lấy thông tin từ listing xác minh đầu tiên; không ghi đè.
        hotel.name = hotel.name or (identity.name[:300] if identity.name else None)
        hotel.address = hotel.address or identity.address
        hotel.city = hotel.city or (identity.city[:120] if identity.city else None)
        if hotel.lat is None and identity.lat is not None:
            hotel.lat, hotel.lng = identity.lat, identity.lng
        if hotel.star_rating is None and identity.star_rating is not None:
            hotel.star_rating = identity.star_rating
        await s.commit()
    log.info("listing_verified", listing_id=listing_id, channel=deps.channel, name=identity.name)
    return "active"


async def _hotel_with_external_id(
    deps: ListingJobDeps, listing_id: int | None, external_id: str | None
) -> int | None:
    """hotel_id của listing KHÁC đã mang `external_id` này (None nếu không có)."""
    if not external_id:
        return None
    async with deps.session_factory() as s:
        stmt = select(Listing.hotel_id).where(
            Listing.channel == deps.channel, Listing.external_id == external_id
        )
        if listing_id is not None:
            stmt = stmt.where(Listing.id != listing_id)
        row = (await s.execute(stmt.limit(1))).first()
    return int(row[0]) if row else None


async def _set_status(
    deps: ListingJobDeps, listing_id: int, status: str | None, error: str
) -> None:
    values: dict[str, object] = {"last_error": error[:1000]}
    stmt = update(Listing).where(Listing.id == listing_id)
    if status is not None:
        values["status"] = status
        # Người dùng đã tạm dừng thì giữ nguyên trạng thái, chỉ ghi lỗi.
        stmt = stmt.where(Listing.status != "paused")
    async with deps.session_factory() as s:
        await s.execute(stmt.values(**values))
        await s.commit()
