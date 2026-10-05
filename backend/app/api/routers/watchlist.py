from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import Principal
from app.api.deps import (
    ApiQueue,
    LocaleDep,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TenantDep,
    WriterDep,
    client_ip,
    ensure_hotel_in_tenant,
    get_queue,
)
from app.api.hotel_views import hotel_out, hotel_outs, listing_out
from app.api.quotas import ensure_can_add_hotel, ensure_can_scan_now
from app.api.scan_now import create_manual_run
from app.api.schemas import (
    ChannelOut,
    ListingAction,
    ListingCreate,
    ListingOut,
    ScanRunOut,
    WatchItemCreate,
    WatchItemOut,
    WatchItemUpdate,
)
from app.audit import record_audit
from app.channels.registry import ListingUrl, UnsupportedUrl, channels, parse_listing_url
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


async def _item(
    session: AsyncSession, link: TenantHotel, hotel: Hotel, *, operator: bool = False
) -> WatchItemOut:
    return WatchItemOut(
        hotel=await hotel_out(session, hotel, operator=operator),
        role=link.role,
        label=link.label,
        active=link.active,
        added_at=link.added_at,
    )


@router.get("", response_model=list[WatchItemOut])
async def list_watchlist(
    tenant_id: TenantDep,
    principal: PrincipalDep,
    session: SessionDep,
    include_inactive: bool = False,
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
    outs = await hotel_outs(session, [h for _, h in rows], operator=principal.is_operator)
    return [
        WatchItemOut(
            hotel=outs[h.id],
            role=link.role,
            label=link.label,
            active=link.active,
            added_at=link.added_at,
        )
        for link, h in rows
    ]


@router.post("", response_model=WatchItemOut, status_code=status.HTTP_201_CREATED)
async def add_hotel(
    body: WatchItemCreate,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    locale: LocaleDep,
    queue: QueueDep = None,
) -> WatchItemOut:
    """Thêm khách sạn bằng URL của bất kỳ kênh hỗ trợ. Listing đã có trong hệ thống (tenant khác
    theo dõi) thì dùng chung khách sạn đó; listing mới được tạo `unverified` và đẩy job kiểm tra
    (tên, toạ độ), sau đó worker tự tìm cùng khách sạn trên các kênh khác (gợi ý chờ xác nhận)."""
    ref = _parse(body.url, locale)
    await ensure_can_add_hotel(session, settings, tenant_id)
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
        if listing.status in ("suggested", "rejected"):
            # Người dùng tự dán đúng URL đang được gợi ý: coi như xác nhận.
            listing.status = "unverified"
            new_listing = True
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
    record_audit(
        session,
        action="watchlist.added",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"hotel:{hotel.id}",
        payload={"channel": ref.channel, "role": body.role, "new_listing": new_listing},
        ip=client_ip(request),
    )
    await session.commit()
    await session.refresh(link)
    if new_listing:
        await _enqueue_verify(queue, listing)
    return await _item(session, link, hotel, operator=principal.is_operator)


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
    hotel_id: int,
    body: WatchItemUpdate,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> WatchItemOut:
    link, hotel = await _tenant_link(session, tenant_id, hotel_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("active") is True and not link.active:
        await ensure_can_add_hotel(session, settings, tenant_id)  # quét lại = thêm vào hạn mức
    for k, v in data.items():
        setattr(link, k, v)
    record_audit(
        session,
        action="watchlist.updated",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"hotel:{hotel_id}",
        payload={"fields": sorted(data)},
        ip=client_ip(request),
    )
    await session.commit()
    return await _item(session, link, hotel, operator=principal.is_operator)


@router.delete("/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    hotel_id: int,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
) -> None:
    link, _hotel = await _tenant_link(session, tenant_id, hotel_id)
    link.active = False  # giữ lịch sử, ngừng quét cho tenant này
    record_audit(
        session,
        action="watchlist.removed",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"hotel:{hotel_id}",
        ip=client_ip(request),
    )
    await session.commit()


@router.post("/{hotel_id}/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
async def add_listing(
    hotel_id: int,
    body: ListingCreate,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
    locale: LocaleDep,
    queue: QueueDep = None,
) -> ListingOut:
    """Gắn thêm một kênh cho khách sạn bằng URL (VD trang Agoda của khách sạn đã có
    trên Booking). Thay URL của kênh đã có chỉ khi tenant là người theo dõi duy nhất."""
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
        # Thay URL của kênh này (sửa gợi ý sai hoặc listing hỏng): listing dùng chung nên ảnh hưởng
        # mọi tenant theo dõi khách sạn → chỉ tenant theo dõi duy nhất hoặc operator. Gợi ý
        # (`suggested`) chưa từng được quét nên tenant nào cũng được thay.
        if current.status != "suggested":
            await _ensure_sole_tracker(session, tenant_id, hotel_id, principal)
        current.listing_key, current.url = ref.listing_key, ref.url
        current.external_id, current.status = ref.external_id, "unverified"
        current.last_error, current.match_score = None, None
        current.not_found_count = 0
    record_audit(
        session,
        action="listing.added",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"hotel:{hotel_id}:{ref.channel}",
        payload={"listing_key": ref.listing_key},
        ip=client_ip(request),
    )
    await session.commit()
    await session.refresh(current)
    await _enqueue_verify(queue, current)
    return listing_out(current, operator=principal.is_operator)


@router.patch("/{hotel_id}/listings/{listing_id}", response_model=ListingOut | None)
async def act_on_listing(
    hotel_id: int,
    listing_id: int,
    body: ListingAction,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
    queue: QueueDep = None,
) -> ListingOut | None:
    await _tenant_link(session, tenant_id, hotel_id, active_only=True)
    listing = (
        await session.execute(
            select(Listing).where(Listing.id == listing_id, Listing.hotel_id == hotel_id)
        )
    ).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "listing not found")
    action = body.action
    # Listing dùng chung giữa tenant: mọi thao tác đổi trạng thái quét của một kênh (tạm dừng, quét
    # lại, thử lại listing hỏng, nhận/bỏ gợi ý) ảnh hưởng tenant khác → chỉ tenant theo dõi duy
    # nhất hoặc operator. Gợi ý chưa được quét nên nhận/bỏ gợi ý chỉ cần là người theo dõi.
    if action in ("pause", "resume", "retry"):
        await _ensure_sole_tracker(session, tenant_id, hotel_id, principal)
    if action == "retry" and listing.status not in ("broken", "unverified"):
        raise HTTPException(status.HTTP_409_CONFLICT, "only broken listings can be retried")
    record_audit(
        session,
        action="listing.action",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"listing:{listing.id}",
        payload={"action": action, "from": listing.status},
        ip=client_ip(request),
    )
    if action == "reject":
        if listing.status != "suggested":
            raise HTTPException(status.HTTP_409_CONFLICT, "only suggestions can be rejected")
        # Giữ dòng `rejected` để lần tìm sau không gợi ý lại đúng listing này.
        listing.status = "rejected"
        await session.commit()
        return None
    if action == "confirm":
        if listing.status != "suggested":
            raise HTTPException(status.HTTP_409_CONFLICT, "listing is not a suggestion")
        listing.status = "unverified"
    elif action == "pause":
        listing.status = "paused"
    elif action in ("resume", "retry"):
        listing.status, listing.last_error = "unverified", None
        listing.not_found_count = 0
    await session.commit()
    await session.refresh(listing)
    if listing.status == "unverified":
        await _enqueue_verify(queue, listing)
    return listing_out(listing, operator=principal.is_operator)


@router.post("/{hotel_id}/discover", status_code=status.HTTP_202_ACCEPTED)
async def discover_listings(
    hotel_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep, queue: QueueDep = None
) -> dict[str, list[str]]:
    """Tìm khách sạn này trên các kênh chưa có listing (kết quả là gợi ý chờ xác nhận)."""
    await _tenant_link(session, tenant_id, hotel_id, active_only=True)
    if queue is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable")
    have = {
        r[0]
        for r in await session.execute(select(Listing.channel).where(Listing.hotel_id == hotel_id))
    }
    todo = [str(c) for c, i in channels().items() if i.collectable and str(c) not in have]
    for channel in todo:
        await queue.enqueue_discover(hotel_id, channel)
    return {"channels": todo}


@router.post("/scan-now", response_model=list[ScanRunOut], status_code=status.HTTP_202_ACCEPTED)
async def scan_now(
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    queue: QueueDep = None,
) -> list[ScanRun]:
    """Quét ngay toàn bộ watchlist của tenant (mỗi kênh một run), không đợi mốc giờ. Có hạn mức
    số lần mỗi ngày (quota_manual_scans_per_day): mỗi lần tốn ngân sách request của cả hệ thống."""
    if not principal.is_operator:
        await ensure_can_scan_now(session, settings, tenant_id)
    return await create_manual_run(session, queue, tenant_id)


@router.post(
    "/{hotel_id}/scan-now", response_model=list[ScanRunOut], status_code=status.HTTP_202_ACCEPTED
)
async def scan_hotel_now(
    hotel_id: int,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    queue: QueueDep = None,
) -> list[ScanRun]:
    """Quét ngay một khách sạn trong watchlist (mỗi kênh đang quét một run nhỏ)."""
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    if not principal.is_operator:
        await ensure_can_scan_now(session, settings, tenant_id)
    return await create_manual_run(session, queue, tenant_id, hotel_id=hotel_id)
