from dataclasses import asdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, RoomType
from app.domain.models import CalendarResult, ProbeMethod, ProbeResult, ProbeStatus, RoomOffer
from app.domain.stock import derive_stock

TERMINAL_STATUSES = (ProbeStatus.OK, ProbeStatus.SOLD_OUT, ProbeStatus.SKIPPED_CALENDAR)


class SnapshotRepository:
    def __init__(self, session: AsyncSession, page_cap: int) -> None:
        self._s = session
        self._page_cap = page_cap

    async def upsert_room_type(self, hotel_id: int, offer: RoomOffer, seen_at: datetime) -> int:
        stmt = (
            insert(RoomType)
            .values(
                hotel_id=hotel_id,
                booking_room_id=offer.booking_room_id,
                name=offer.name,
                max_occupancy=offer.max_occupancy,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[RoomType.hotel_id, RoomType.booking_room_id],
                set_={
                    "name": offer.name,
                    "max_occupancy": offer.max_occupancy,
                    "last_seen_at": seen_at,
                },
            )
            .returning(RoomType.id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def _upsert_probe(
        self,
        *,
        scan_run_id: int,
        hotel_id: int,
        stay_date: date,
        checkin: date,
        checkout: date,
        nights: int,
        adults: int,
        status: str,
        method: str | None,
        proxy_country: str | None,
        session_id: str | None,
        http_status: int | None,
        raw_object_key: str | None,
        parser_version: str | None,
        error: str | None,
        fetched_at: datetime,
        duration_ms: int,
    ) -> int:
        values = dict(
            scan_run_id=scan_run_id,
            hotel_id=hotel_id,
            stay_date=stay_date,
            checkin=checkin,
            checkout=checkout,
            nights=nights,
            adults=adults,
            status=status,
            method=method,
            proxy_country=proxy_country,
            session_id=session_id,
            http_status=http_status,
            raw_object_key=raw_object_key,
            parser_version=parser_version,
            error=error,
            fetched_at=fetched_at,
            duration_ms=duration_ms,
        )
        update_cols = {
            k: v for k, v in values.items() if k not in ("scan_run_id", "hotel_id", "stay_date")
        }
        stmt = (
            insert(Probe)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Probe.scan_run_id, Probe.hotel_id, Probe.stay_date],
                set_=update_cols,
            )
            .returning(Probe.id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def write_probe(
        self,
        scan_run_id: int,
        hotel_id: int,
        stay_date: date,
        result: ProbeResult,
        raw_object_key: str | None,
        parser_version: str,
        proxy_country: str | None,
        fetched_at: datetime,
    ) -> int:
        probe_id = await self._upsert_probe(
            scan_run_id=scan_run_id,
            hotel_id=hotel_id,
            stay_date=stay_date,
            checkin=result.checkin,
            checkout=result.checkout,
            nights=result.nights,
            adults=result.adults,
            status=str(result.status),
            method=str(result.method),
            proxy_country=proxy_country,
            session_id=result.session_id,
            http_status=result.http_status,
            raw_object_key=raw_object_key,
            parser_version=parser_version,
            error=result.error,
            fetched_at=fetched_at,
            duration_ms=result.duration_ms,
        )
        await self._s.execute(delete(RoomSnapshot).where(RoomSnapshot.probe_id == probe_id))
        for offer in result.offers:
            room_type_id = await self.upsert_room_type(hotel_id, offer, fetched_at)
            stock = derive_stock(offer.badge_count, offer.dropdown_max, self._page_cap)
            self._s.add(
                RoomSnapshot(
                    probe_id=probe_id,
                    hotel_id=hotel_id,
                    room_type_id=room_type_id,
                    stay_date=stay_date,
                    scanned_at=fetched_at,
                    rooms_left=stock.rooms_left,
                    stock_confidence=str(stock.confidence),
                    badge_count=offer.badge_count,
                    dropdown_max=offer.dropdown_max,
                    min_price=offer.min_price,
                    min_refundable_price=offer.min_refundable_price,
                    currency=offer.currency,
                    rates=[{**asdict(r), "price": str(r.price)} for r in offer.rates],
                )
            )
        if result.booking_hotel_id or result.hotel_name:
            await self.update_hotel_identity(hotel_id, result.booking_hotel_id, result.hotel_name)
        await self._s.flush()
        return probe_id

    async def write_skipped(
        self,
        scan_run_id: int,
        hotel_id: int,
        stay_date: date,
        nights: int,
        adults: int,
        fetched_at: datetime,
    ) -> int:
        probe_id = await self._upsert_probe(
            scan_run_id=scan_run_id,
            hotel_id=hotel_id,
            stay_date=stay_date,
            checkin=stay_date,
            checkout=stay_date + timedelta(days=nights),
            nights=nights,
            adults=adults,
            status=str(ProbeStatus.SKIPPED_CALENDAR),
            method=str(ProbeMethod.CALENDAR),
            proxy_country=None,
            session_id=None,
            http_status=None,
            raw_object_key=None,
            parser_version=None,
            error=None,
            fetched_at=fetched_at,
            duration_ms=0,
        )
        await self._s.execute(delete(RoomSnapshot).where(RoomSnapshot.probe_id == probe_id))
        await self._s.flush()
        return probe_id

    async def write_calendar(
        self, hotel_id: int, scan_run_id: int, result: CalendarResult, fetched_at: datetime
    ) -> None:
        if not result.ok:
            return
        for day in result.days:
            stmt = (
                insert(HotelCalendar)
                .values(
                    hotel_id=hotel_id,
                    scan_run_id=scan_run_id,
                    stay_date=day.checkin,
                    available=day.available,
                    min_length_of_stay=day.min_length_of_stay,
                    avg_price_display=day.avg_price_display,
                    fetched_at=fetched_at,
                )
                .on_conflict_do_update(
                    index_elements=[
                        HotelCalendar.hotel_id,
                        HotelCalendar.scan_run_id,
                        HotelCalendar.stay_date,
                    ],
                    set_={
                        "available": day.available,
                        "min_length_of_stay": day.min_length_of_stay,
                        "avg_price_display": day.avg_price_display,
                        "fetched_at": fetched_at,
                    },
                )
            )
            await self._s.execute(stmt)
        await self._s.flush()

    async def update_hotel_identity(
        self, hotel_id: int, booking_hotel_id: str | None, name: str | None
    ) -> None:
        values: dict[str, str] = {}
        if booking_hotel_id:
            values["booking_hotel_id"] = booking_hotel_id
        if name:
            values["name"] = name[:300]
        if values:
            await self._s.execute(update(Hotel).where(Hotel.id == hotel_id).values(**values))

    async def terminal_dates(self, scan_run_id: int, hotel_id: int) -> set[date]:
        rows = await self._s.execute(
            select(Probe.stay_date).where(
                Probe.scan_run_id == scan_run_id,
                Probe.hotel_id == hotel_id,
                Probe.status.in_([str(s) for s in TERMINAL_STATUSES]),
            )
        )
        return {r[0] for r in rows}
