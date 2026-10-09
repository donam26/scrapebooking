from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import load_compset, review_compset
from app.api.auth import Principal
from app.api.deps import (
    ApiQueue,
    LocaleDep,
    SessionDep,
    TenantDep,
    WriterDep,
    ensure_hotel_in_tenant,
    get_queue,
)
from app.api.hotel_views import hotel_out, hotel_outs
from app.api.scan_now import create_manual_run
from app.api.schemas import (
    ChannelOut,
    CompsetReviewOut,
    ListingAction,
    ListingCreate,
    ListingOut,
    ScanRunOut,
    WatchItemCreate,
    WatchItemOut,
    WatchItemUpdate,
)
from app.channels.registry import (
    ListingUrl,
    UnsupportedUrl,
    channels,
    parse_listing_url,
)
from app.db.models import Hotel, Listing, ScanRun, TenantHotel
from app.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
channels_router = APIRouter(tags=["watchlist"])

QueueDep = Annotated[ApiQueue | None, Depends(get_queue)]


@channels_router.get("/channels", response_model=list[ChannelOut])
async def list_channels() -> list[ChannelOut]:
    """Kênh hệ thống nhận diện được URL; `collectable` = đã quét được."""
    return [
        ChannelOut(
            code=str(i.code),
            name=i.name,
            example_url=i.example_url,
            hosts=list(i.hosts),
            collectable=i.collectable,
        )
        for i in channels().values()
    ]


def _parse(url: str, locale: str) -> ListingUrl:
    """Lỗi URL là câu hướng dẫn cho người dùng (dạng URL đúng của kênh): dịch ở đây theo ngôn ngữ
    request, khác các `detail` tiếng Anh ổn định khác."""
    try:
        return parse_listing_url(url)
    except UnsupportedUrl as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.message(locale)) from exc


async def _enqueue_verify(queue: ApiQueue | None, listing: Listing) -> None:
    if queue is None:
        return
    try:
        await queue.enqueue_verify(listing.id, listing.channel)
    except Exception:  # noqa: BLE001 — listing vẫn được tạo; worker/CLI kiểm tra lại sau
        log.exception("enqueue_verify_failed", listing_id=listing.id)


async def _item(session: AsyncSession, link: TenantHotel, hotel: Hotel) -> WatchItemOut:
    return WatchItemOut(
        hotel=await hotel_out(session, hotel),
        role=link.role,
        label=link.label,
        active=link.active,
        added_at=link.added_at,
        compset_of=link.compset_of,
        tier=link.tier or "primary",
        weight=link.weight if link.weight is not None else Decimal(1),
    )


@router.get("", response_model=list[WatchItemOut])
async def list_watchlist(
    tenant_id: TenantDep, session: SessionDep, include_inactive: bool = False
) -> list[WatchItemOut]:
    stmt = (
        select(TenantHotel, Hotel)
        .join(Hotel, Hotel.id == TenantHotel.hotel_id)
        .where(TenantHotel.tenant_id == tenant_id)
        .order_by(TenantHotel.role.desc(), TenantHotel.added_at)  # self trước competitor
    )
    if not include_inactive:
        stmt = stmt.where(TenantHotel.active.is_(True))
    rows = (await session.execute(stmt)).all()
    outs = await hotel_outs(session, [h for _, h in rows])
    return [
        WatchItemOut(
            hotel=outs[h.id],
            role=link.role,
            label=link.label,
            active=link.active,
            added_at=link.added_at,
            compset_of=link.compset_of,
            tier=link.tier or "primary",
            weight=link.weight if link.weight is not None else Decimal(1),
        )
        for link, h in rows
    ]


@router.get("/compset-review", response_model=CompsetReviewOut)
async def compset_review(
    tenant_id: TenantDep, session: SessionDep, own_hotel_id: int | None = None
) -> CompsetReviewOut:
    """Rà soát compset của một khách sạn của bạn theo quy tắc CoStar STR (7.3)."""
    w = await load_compset(session, tenant_id, own_hotel_id)
    own = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    ids = w.competitors
    rooms: dict[int, int | None] = {}
    if ids:
        for hid, total in await session.execute(
            select(Hotel.id, Hotel.rooms_total).where(Hotel.id.in_(ids))
        ):
            rooms[hid] = total
    last = (
        await session.execute(
            select(func.max(TenantHotel.added_at)).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.role == "competitor"
            )
        )
    ).scalar_one()
    r = review_compset(ids, rooms, last, datetime.now(tz=UTC))
    return CompsetReviewOut(
        own_hotel_id=own,
        primary=len(ids),
        secondary=len(w.secondary),
        rooms_known=r.rooms_known,
        warnings=r.warnings,
        dominant_hotel_id=r.dominant_hotel_id,
        dominant_share=r.dominant_share,
        last_change_at=last,
    )


@router.post("", response_model=WatchItemOut, status_code=status.HTTP_201_CREATED)
async def add_hotel(
    body: WatchItemCreate,
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    locale: LocaleDep,
    queue: QueueDep = None,
) -> WatchItemOut:
    """Thêm khách sạn bằng URL Booking.com. Listing đã có trong hệ thống (tenant khác theo dõi) thì
    dùng chung khách sạn đó; listing mới được tạo `unverified` và đẩy job kiểm tra (tên, toạ độ)."""
    ref = _parse(body.url, locale)
    listing = (
        await session.execute(
            select(Listing).where(
                Listing.channel == ref.channel, Listing.listing_key == ref.listing_key
            )
        )
    ).scalar_one_or_none()
    new_listing = listing is None
    if listing is None:
        try:
            async with session.begin_nested():
                hotel = Hotel(country_code=ref.country_code or "vn")
                session.add(hotel)
                await session.flush()
                listing = Listing(
                    hotel_id=hotel.id,
                    channel=ref.channel,
                    listing_key=ref.listing_key,
                    external_id=ref.external_id,
                    url=ref.url,
                    status="unverified",
                )
                session.add(listing)
                await session.flush()
        except IntegrityError:
            # Hai yêu cầu cùng URL chạy song song: bên sau dùng listing bên trước vừa tạo.
            listing = None
            new_listing = False
    if listing is None:
        listing = (
            await session.execute(
                select(Listing).where(
                    Listing.channel == ref.channel, Listing.listing_key == ref.listing_key
                )
            )
        ).scalar_one()
    if not new_listing:
        hotel = (
            await session.execute(select(Hotel).where(Hotel.id == listing.hotel_id))
        ).scalar_one()
    link = (
        await session.execute(
            select(TenantHotel).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        link = TenantHotel(
            tenant_id=tenant_id, hotel_id=hotel.id, role=body.role, label=body.label, active=True
        )
        session.add(link)
    else:
        link.role, link.label, link.active = body.role, body.label, True
    await session.commit()
    await session.refresh(link)
    if new_listing:
        await _enqueue_verify(queue, listing)
    return await _item(session, link, hotel)


async def _tenant_link(
    session: AsyncSession, tenant_id: int, hotel_id: int, active_only: bool = False
) -> tuple[TenantHotel, Hotel]:
    stmt = (
        select(TenantHotel, Hotel)
        .join(Hotel, Hotel.id == TenantHotel.hotel_id)
        .where(TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id)
    )
    if active_only:
        stmt = stmt.where(TenantHotel.active.is_(True))
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not in watchlist")
    return row[0], row[1]


async def _ensure_sole_tracker(
    session: AsyncSession, tenant_id: int, hotel_id: int, principal: Principal
) -> None:
    """Listing dùng chung giữa tenant: đổi URL, tạm dừng hay quét lại một kênh ảnh hưởng mọi tenant
    theo dõi khách sạn đó. Chỉ cho phép khi tenant này là người theo dõi duy nhất, hoặc operator."""
    if principal.is_operator:
        return
    others = (
        await session.execute(
            select(TenantHotel.tenant_id).where(
                TenantHotel.hotel_id == hotel_id,
                TenantHotel.tenant_id != tenant_id,
                TenantHotel.active.is_(True),
            )
        )
    ).first()
    if others is not None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "hotel is tracked by other tenants; ask an operator to change or pause its channels",
        )


@router.patch("/{hotel_id}", response_model=WatchItemOut)
async def update_item(
    hotel_id: int, body: WatchItemUpdate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> WatchItemOut:
    link, hotel = await _tenant_link(session, tenant_id, hotel_id)
    data = body.model_dump(exclude_unset=True)
    if "rooms_total" in data:
        hotel.rooms_total = data.pop("rooms_total")
    if data.get("compset_of") is not None:
        own = await session.execute(
            select(TenantHotel.hotel_id).where(
                TenantHotel.tenant_id == tenant_id,
                TenantHotel.hotel_id == data["compset_of"],
                TenantHotel.role == "self",
            )
        )
        if own.first() is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "compset_of must be one of your hotels"
            )
    for k, v in data.items():
        setattr(link, k, v)
    await session.commit()
    return await _item(session, link, hotel)


@router.delete("/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    hotel_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> None:
    link, _hotel = await _tenant_link(session, tenant_id, hotel_id)
    link.active = False  # giữ lịch sử, ngừng quét cho tenant này
    await session.commit()


@router.post("/{hotel_id}/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
async def add_listing(
    hotel_id: int,
    body: ListingCreate,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    locale: LocaleDep,
    queue: QueueDep = None,
) -> Listing:
    """Sửa URL Booking.com của khách sạn (listing hỏng hoặc dán nhầm). Thay URL đang quét chỉ khi
    tenant là người theo dõi duy nhất."""
    await _tenant_link(session, tenant_id, hotel_id, active_only=True)
    ref = _parse(body.url, locale)
    taken = (
        await session.execute(
            select(Listing).where(
                Listing.channel == ref.channel, Listing.listing_key == ref.listing_key
            )
        )
    ).scalar_one_or_none()
    if taken is not None and taken.hotel_id != hotel_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "url already linked to another hotel",
        )
    current = (
        await session.execute(
            select(Listing).where(Listing.hotel_id == hotel_id, Listing.channel == ref.channel)
        )
    ).scalar_one_or_none()
    if current is None:
        current = Listing(
            hotel_id=hotel_id,
            channel=ref.channel,
            listing_key=ref.listing_key,
            url=ref.url,
            external_id=ref.external_id,
            status="unverified",
        )
        session.add(current)
    elif current.listing_key == ref.listing_key and current.status in ("active", "unverified"):
        return current  # dán lại đúng URL đang quét: không đặt lại trạng thái
    else:
        # Thay URL (sửa listing hỏng): ảnh hưởng tenant khác.
        if current.status != "broken":
            await _ensure_sole_tracker(session, tenant_id, hotel_id, principal)
        current.listing_key, current.url = ref.listing_key, ref.url
        current.external_id, current.status = ref.external_id, "unverified"
        current.last_error, current.match_score = None, None
    await session.commit()
    await session.refresh(current)
    await _enqueue_verify(queue, current)
    return current


@router.patch("/{hotel_id}/listings/{listing_id}", response_model=ListingOut | None)
async def act_on_listing(
    hotel_id: int,
    listing_id: int,
    body: ListingAction,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    queue: QueueDep = None,
) -> Listing | None:
    await _tenant_link(session, tenant_id, hotel_id, active_only=True)
    listing = (
        await session.execute(
            select(Listing).where(Listing.id == listing_id, Listing.hotel_id == hotel_id)
        )
    ).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "listing not found")
    action = body.action
    if action in ("pause", "resume"):
        await _ensure_sole_tracker(session, tenant_id, hotel_id, principal)
    if action == "retry" and listing.status not in ("broken", "unverified"):
        raise HTTPException(status.HTTP_409_CONFLICT, "only broken listings can be retried")
    if action == "pause":
        listing.status = "paused"
    elif action in ("resume", "retry"):
        listing.status, listing.last_error = "unverified", None
    await session.commit()
    await session.refresh(listing)
    if listing.status == "unverified":
        await _enqueue_verify(queue, listing)
    return listing


@router.post("/scan-now", response_model=list[ScanRunOut], status_code=status.HTTP_202_ACCEPTED)
async def scan_now(
    tenant_id: TenantDep, _: WriterDep, session: SessionDep, queue: QueueDep = None
) -> list[ScanRun]:
    """Quét ngay toàn bộ watchlist của tenant (mỗi kênh một run), không đợi mốc giờ."""
    return await create_manual_run(session, queue, tenant_id)


@router.post(
    "/{hotel_id}/scan-now", response_model=list[ScanRunOut], status_code=status.HTTP_202_ACCEPTED
)
async def scan_hotel_now(
    hotel_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep, queue: QueueDep = None
) -> list[ScanRun]:
    """Quét ngay một khách sạn trong watchlist (mỗi kênh đang quét một run nhỏ)."""
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    return await create_manual_run(session, queue, tenant_id, hotel_id=hotel_id)
