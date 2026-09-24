from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep, TenantDep, WriterDep
from app.api.schemas import HotelOut, WatchItemCreate, WatchItemOut, WatchItemUpdate
from app.db.models import Hotel, TenantHotel
from app.domain.booking_url import BookingUrlError, parse_booking_url

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _item(link: TenantHotel, hotel: Hotel) -> WatchItemOut:
    return WatchItemOut(
        hotel=HotelOut.model_validate(hotel),
        role=link.role,
        label=link.label,
        active=link.active,
        added_at=link.added_at,
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
    return [_item(link, hotel) for link, hotel in (await session.execute(stmt)).all()]


@router.post("", response_model=WatchItemOut, status_code=status.HTTP_201_CREATED)
async def add_hotel(
    body: WatchItemCreate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> WatchItemOut:
    try:
        ref = parse_booking_url(body.booking_url)
    except BookingUrlError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    hotel = (
        await session.execute(select(Hotel).where(Hotel.booking_slug == ref.slug))
    ).scalar_one_or_none()
    if hotel is None:
        hotel = Hotel(
            booking_url=ref.canonical_url, booking_slug=ref.slug, country_code=ref.country_code
        )
        session.add(hotel)
        await session.flush()
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
    return _item(link, hotel)


@router.patch("/{hotel_id}", response_model=WatchItemOut)
async def update_item(
    hotel_id: int, body: WatchItemUpdate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> WatchItemOut:
    row = (
        await session.execute(
            select(TenantHotel, Hotel)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not in watchlist")
    link, hotel = row
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(link, k, v)
    await session.commit()
    return _item(link, hotel)


@router.delete("/{hotel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    hotel_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> None:
    link = (
        await session.execute(
            select(TenantHotel).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not in watchlist")
    link.active = False  # giữ lịch sử, ngừng quét cho tenant này
    await session.commit()
