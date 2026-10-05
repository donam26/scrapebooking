"""Job vòng đời listing (D8), chạy trên hàng đợi của kênh (worker có session/proxy của kênh).

- verify_listing: URL người dùng dán → kênh trả khách sạn nào (tên, id, toạ độ) → active | broken.
- discover_listing: tìm cùng khách sạn trên kênh này theo tên + toạ độ → listing `suggested` chờ
  người dùng xác nhận (không bao giờ tự gắn: sai định danh làm hỏng compset).
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.registry import channels
from app.clock import Clock
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import ChannelCollector
from app.db.models import Hotel, Listing
from app.domain.models import ListingQuery, ListingRef
from app.logging import get_logger
from app.repo.snapshots import SnapshotRepository

log = get_logger(__name__)

# Điểm khớp tối thiểu để đưa thành gợi ý (người dùng vẫn phải xác nhận).
SUGGEST_MIN_SCORE = 0.7


class ListingRetry(RuntimeError):
    """Bị chặn khi verify/discover: để arq thử lại sau."""


@dataclass
class ListingJobDeps:
    session_factory: async_sessionmaker[AsyncSession]
    collector: ChannelCollector
    clock: Clock
    channel: str
    enqueue_discover: object | None = None  # async (hotel_id, channel) -> None
    # Số lần kênh báo "không tồn tại" liên tiếp trước khi listing thành `broken`.
    not_found_threshold: int = 3


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
    except ListingNotFound as exc:
        # Kênh nói rõ không tồn tại (404 thật / mã riêng). Đếm chuỗi qua các lần thử (mỗi lần cách
        # nhau, có thể session/proxy khác): đủ ngưỡng mới `broken`, chặn mềm trả 404 giả không
        # giết listing; URL sai thật vẫn thành broken trong một job (3 lần thử).
        if await _record_not_found(deps, ref):
            return "broken"
        if not final_attempt:
            raise ListingRetry(str(exc)) from exc
        return "not_found"
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
        # Hai URL khác nhau cùng trỏ một khách sạn của kênh (VD slug Agoda đổi, có redirect): không
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
        listing.not_found_count = 0
        # Khách sạn (property) lấy thông tin từ listing xác minh đầu tiên; không ghi đè.
        hotel.name = hotel.name or (identity.name[:300] if identity.name else None)
        hotel.address = hotel.address or identity.address
        hotel.city = hotel.city or (identity.city[:120] if identity.city else None)
        if hotel.lat is None and identity.lat is not None:
            hotel.lat, hotel.lng = identity.lat, identity.lng
        if hotel.star_rating is None and identity.star_rating is not None:
            hotel.star_rating = identity.star_rating
        hotel_id = hotel.id
        existing = {
            r[0]
            for r in await s.execute(select(Listing.channel).where(Listing.hotel_id == hotel_id))
        }
        await s.commit()
    log.info("listing_verified", listing_id=listing_id, channel=deps.channel, name=identity.name)
    if deps.enqueue_discover is not None:
        for code, info in channels().items():
            if info.collectable and str(code) not in existing:
                await deps.enqueue_discover(hotel_id, str(code))  # type: ignore[operator]
    return "active"


async def _hotel_with_external_id(
    deps: ListingJobDeps,
    listing_id: int | None,
    external_id: str | None,
    channel: str | None = None,
) -> int | None:
    """hotel_id của listing KHÁC cùng kênh đã mang `external_id` này (None nếu không có)."""
    if not external_id:
        return None
    async with deps.session_factory() as s:
        stmt = select(Listing.hotel_id).where(
            Listing.channel == (channel or deps.channel), Listing.external_id == external_id
        )
        if listing_id is not None:
            stmt = stmt.where(Listing.id != listing_id)
        row = (await s.execute(stmt.limit(1))).first()
    return int(row[0]) if row else None


async def _record_not_found(deps: ListingJobDeps, ref: ListingRef) -> bool:
    """Tăng đếm not_found của listing (khoá (hotel_id, channel)); True khi vừa thành broken."""
    async with deps.session_factory() as s:
        broken = await SnapshotRepository(s, page_cap=0).record_not_found(
            ref.hotel_id, ref.channel, "not_found", deps.not_found_threshold
        )
        await s.commit()
    return broken


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


async def run_discover_listing(deps: ListingJobDeps, hotel_id: int, final_attempt: bool) -> str:
    async with deps.session_factory() as s:
        hotel = (await s.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one_or_none()
        if hotel is None or not hotel.name:
            return "no-hotel"
        already = (
            await s.execute(
                select(Listing.id).where(
                    Listing.hotel_id == hotel_id, Listing.channel == deps.channel
                )
            )
        ).first()
        if already is not None:
            return "exists"
        query = ListingQuery(
            name=hotel.name,
            city=hotel.city,
            country_code=hotel.country_code,
            lat=hotel.lat,
            lng=hotel.lng,
        )
    try:
        candidates = await deps.collector.suggest(query)
    except ListingBlocked as exc:
        if not final_attempt:
            raise ListingRetry(str(exc)) from exc
        return "blocked"
    except Exception as exc:  # noqa: BLE001
        log.warning("listing_discover_error", hotel_id=hotel_id, error=repr(exc))
        if not final_attempt:
            raise ListingRetry(repr(exc)) from exc
        return "error"
    best = None
    for c in candidates:
        if c.score < SUGGEST_MIN_SCORE:
            continue
        taken = await _hotel_with_external_id(deps, None, c.external_id, channel=deps.channel)
        if taken is None or taken == hotel_id:
            best = c
            break
    if best is None:
        log.info("listing_discover_none", hotel_id=hotel_id, channel=deps.channel)
        return "none"
    async with deps.session_factory() as s:
        s.add(
            Listing(
                hotel_id=hotel_id,
                channel=deps.channel,
                listing_key=best.listing_key[:300],
                external_id=(best.external_id or None),
                url=best.url,
                name=best.name[:300] if best.name else None,
                status="suggested",
                match_score=Decimal(str(round(best.score, 3))),
            )
        )
        try:
            await s.commit()
        except IntegrityError:
            # Listing này đã thuộc một khách sạn khác (cùng property được thêm hai lần
            # qua hai kênh khác nhau): không tự gộp.
            await s.rollback()
            log.warning(
                "listing_discover_conflict",
                hotel_id=hotel_id,
                channel=deps.channel,
                listing_key=best.listing_key,
            )
            return "conflict"
    log.info("listing_suggested", hotel_id=hotel_id, channel=deps.channel, score=best.score)
    return "suggested"
