from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.api.deps import SessionDep, TenantDep, ensure_hotel_in_tenant, tenant_hotel_ids
from app.api.schemas import (
    CompsetDayOut,
    DateCell,
    DayDetailOut,
    EventOut,
    HotelDateSnapshotOut,
    HotelDetailOut,
    HotelOut,
    HotelRow,
    OverviewOut,
    RoomSnapshotOut,
    RoomTypeOut,
    ScanRunOut,
)
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    Probe,
    RoomSnapshot,
    RoomType,
    ScanJob,
    ScanRun,
    Tenant,
    TenantHotel,
)
from app.domain.models import ProbeStatus

router = APIRouter(tags=["data"])

MAX_RANGE_DAYS = 120


async def _local_today(session: AsyncSession, tenant_id: int) -> date:
    tenant = await session.get(Tenant, tenant_id)
    tz: ZoneInfo | timezone = UTC
    if tenant:
        try:
            tz = ZoneInfo(tenant.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = UTC  # dữ liệu cũ có múi giờ sai không được làm hỏng màn hình
    return datetime.now(tz=UTC).astimezone(tz).date()


def _range(
    start: date | None, end: date | None, today: date, default_days: int = 30
) -> tuple[date, date]:
    s = start or today
    e = end or s + timedelta(days=default_days - 1)
    if e < s:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end before start")
    if (e - s).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"range over {MAX_RANGE_DAYS} days"
        )
    return s, e


def _cell(d: date, m: HotelDateMetric | None) -> DateCell:
    if m is None:
        return DateCell(
            stay_date=d,
            availability_status=None,
            exact_rooms_left=None,
            min_price=None,
            currency=None,
            pickup_24h=None,
            velocity_3d=None,
            price_change_7d_pct=None,
            exact_share=None,
            sold_out_at=None,
            restocked_at=None,
            last_observed_at=None,
            days_to_arrival=None,
        )
    return DateCell(
        stay_date=d,
        availability_status=m.availability_status,
        exact_rooms_left=m.exact_rooms_left,
        min_price=m.min_price,
        currency=m.currency,
        pickup_24h=m.pickup_24h,
        velocity_3d=m.velocity_3d,
        price_change_7d_pct=m.price_change_7d_pct,
        exact_share=m.exact_share,
        sold_out_at=m.sold_out_at,
        restocked_at=m.restocked_at,
        last_observed_at=m.last_observed_at,
        days_to_arrival=m.days_to_arrival,
    )


async def _events_out(session: AsyncSession, stmt: Select[Any]) -> list[EventOut]:
    rows = (await session.execute(stmt)).all()
    return [
        EventOut(
            id=e.id,
            hotel_id=e.hotel_id,
            hotel_name=h.name,
            hotel_slug=h.booking_slug,
            room_type_id=e.room_type_id,
            room_type_name=rt_name,
            stay_date=e.stay_date,
            event_type=e.event_type,
            from_value=e.from_value,
            to_value=e.to_value,
            delta=e.delta,
            confidence=e.confidence,
            previous_scan_run_id=e.previous_scan_run_id,
            scan_run_id=e.scan_run_id,
            observed_at=e.observed_at,
        )
        for e, h, rt_name in rows
    ]


def _events_stmt() -> Select[Any]:
    return (
        select(AvailabilityEvent, Hotel, RoomType.name)
        .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
        .outerjoin(RoomType, RoomType.id == AvailabilityEvent.room_type_id)
    )


async def _tenant_runs(
    session: AsyncSession, tenant_id: int, limit: int, finished_only: bool
) -> list[ScanRunOut]:
    """Run là chung toàn hệ thống: tenant chỉ thấy run có khách sạn của mình, với số job/probe
    và trạng thái tính riêng trên các khách sạn đó (không lộ số liệu của tenant khác)."""
    hotel_ids = await tenant_hotel_ids(session, tenant_id, include_inactive=True)
    if not hotel_ids:
        return []
    touches_tenant = or_(
        exists().where(ScanJob.scan_run_id == ScanRun.id, ScanJob.hotel_id.in_(hotel_ids)),
        exists().where(Probe.scan_run_id == ScanRun.id, Probe.hotel_id.in_(hotel_ids)),
    )
    stmt = select(ScanRun).where(touches_tenant)
    if finished_only:
        stmt = stmt.where(ScanRun.status.in_(["completed", "partial"])).order_by(
            ScanRun.finished_at.desc()
        )
    else:
        stmt = stmt.order_by(ScanRun.id.desc())
    runs = list((await session.execute(stmt.limit(limit))).scalars())
    if not runs:
        return []
    run_ids = [r.id for r in runs]
    jobs: dict[int, tuple[int, int]] = {
        row[0]: (row[1], row[2] or 0)
        for row in await session.execute(
            select(
                ScanJob.scan_run_id,
                func.count(),
                func.count().filter(ScanJob.status == "failed"),
            )
            .where(ScanJob.scan_run_id.in_(run_ids), ScanJob.hotel_id.in_(hotel_ids))
            .group_by(ScanJob.scan_run_id)
        )
    }
    probes: dict[int, dict[str, int]] = {}
    for run_id, status_, n in await session.execute(
        select(Probe.scan_run_id, Probe.status, func.count())
        .where(Probe.scan_run_id.in_(run_ids), Probe.hotel_id.in_(hotel_ids))
        .group_by(Probe.scan_run_id, Probe.status)
    ):
        probes.setdefault(run_id, {})[status_] = n
    out = []
    for r in runs:
        total_jobs, failed_jobs = jobs.get(r.id, (0, 0))
        by_status = probes.get(r.id, {})
        status_ = r.status
        if status_ in ("completed", "partial"):
            status_ = "partial" if failed_jobs else "completed"
        out.append(
            ScanRunOut(
                id=r.id,
                trigger_key=r.trigger_key,
                scheduled_at=r.scheduled_at,
                started_at=r.started_at,
                finished_at=r.finished_at,
                status=status_,
                total_jobs=total_jobs,
                total_probes=sum(by_status.values()),
                ok_count=by_status.get(str(ProbeStatus.OK), 0),
                sold_out_count=by_status.get(str(ProbeStatus.SOLD_OUT), 0)
                + by_status.get(str(ProbeStatus.SKIPPED_CALENDAR), 0),
                blocked_count=by_status.get(str(ProbeStatus.BLOCKED), 0),
                error_count=by_status.get(str(ProbeStatus.ERROR), 0),
            )
        )
    return out


@router.get("/overview", response_model=OverviewOut)
async def overview(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> OverviewOut:
    s, e = _range(start, end, await _local_today(session, tenant_id))
    links = (
        await session.execute(
            select(TenantHotel, Hotel)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
            .order_by(TenantHotel.role.desc(), TenantHotel.added_at)
        )
    ).all()
    hotel_ids = [h.id for _, h in links]
    metrics: dict[tuple[int, date], HotelDateMetric] = {}
    if hotel_ids:
        rows = (
            await session.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id.in_(hotel_ids),
                    HotelDateMetric.stay_date >= s,
                    HotelDateMetric.stay_date <= e,
                )
            )
        ).scalars()
        metrics = {(m.hotel_id, m.stay_date): m for m in rows}
    days = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    hotels = [
        HotelRow(
            hotel=HotelOut.model_validate(h),
            role=link.role,
            label=link.label,
            cells=[_cell(d, metrics.get((h.id, d))) for d in days],
        )
        for link, h in links
    ]
    compset = [CompsetDayOut(**c.__dict__) for c in await compset_by_day(session, tenant_id, s, e)]
    last_runs = await _tenant_runs(session, tenant_id, limit=1, finished_only=True)
    return OverviewOut(
        start=s,
        end=e,
        hotels=hotels,
        compset=compset,
        last_run=last_runs[0] if last_runs else None,
    )


@router.get("/hotels/{hotel_id}", response_model=HotelDetailOut)
async def hotel_detail(
    hotel_id: int,
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
    event_limit: int = Query(200, ge=1, le=1000),
) -> HotelDetailOut:
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    s, e = _range(start, end, await _local_today(session, tenant_id))
    row = (
        await session.execute(
            select(TenantHotel, Hotel)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id)
        )
    ).one()
    link, hotel = row
    metrics = {
        m.stay_date: m
        for m in (
            await session.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id == hotel_id,
                    HotelDateMetric.stay_date >= s,
                    HotelDateMetric.stay_date <= e,
                )
            )
        ).scalars()
    }
    days = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    events = await _events_out(
        session,
        _events_stmt()
        .where(AvailabilityEvent.hotel_id == hotel_id)
        .order_by(AvailabilityEvent.observed_at.desc(), AvailabilityEvent.id.desc())
        .limit(event_limit),
    )
    return HotelDetailOut(
        hotel=HotelOut.model_validate(hotel),
        role=link.role,
        label=link.label,
        metrics=[_cell(d, metrics.get(d)) for d in days],
        events=events,
    )


@router.get("/hotels/{hotel_id}/dates/{stay_date}", response_model=DayDetailOut)
async def day_detail(
    hotel_id: int,
    stay_date: date,
    tenant_id: TenantDep,
    session: SessionDep,
    history_days: int = Query(14, ge=1, le=60),
) -> DayDetailOut:
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not found")
    since = datetime.now(tz=UTC) - timedelta(days=history_days)
    history = list(
        (
            await session.execute(
                select(RoomSnapshot)
                .where(
                    RoomSnapshot.hotel_id == hotel_id,
                    RoomSnapshot.stay_date == stay_date,
                    RoomSnapshot.scanned_at >= since,
                )
                .order_by(RoomSnapshot.scanned_at, RoomSnapshot.room_type_id)
            )
        ).scalars()
    )
    rt_ids = {r.room_type_id for r in history}
    room_types = (
        list(
            (
                await session.execute(
                    select(RoomType).where(RoomType.id.in_(rt_ids)).order_by(RoomType.name)
                )
            ).scalars()
        )
        if rt_ids
        else []
    )
    observations = list(
        (
            await session.execute(
                select(HotelDateSnapshot)
                .where(
                    HotelDateSnapshot.hotel_id == hotel_id,
                    HotelDateSnapshot.stay_date == stay_date,
                    HotelDateSnapshot.scanned_at >= since,
                )
                .order_by(HotelDateSnapshot.scanned_at)
            )
        ).scalars()
    )
    events = await _events_out(
        session,
        _events_stmt()
        .where(AvailabilityEvent.hotel_id == hotel_id, AvailabilityEvent.stay_date == stay_date)
        .order_by(AvailabilityEvent.observed_at.desc()),
    )
    # Lần quét gần nhất lấy theo quan sát (gồm cả hết phòng/không rõ, vốn không có snapshot loại
    # phòng); snapshot mới hơn quan sát nghĩa là analytics chưa chạy xong cho lần quét đó.
    rooms_at = max((r.scanned_at for r in history), default=None)
    last_obs = observations[-1] if observations else None
    latest_at: datetime | None
    latest_status: str | None
    if last_obs is not None and (rooms_at is None or last_obs.scanned_at >= rooms_at):
        latest_at, latest_status = last_obs.scanned_at, last_obs.status
    else:
        latest_at, latest_status = rooms_at, ("available" if rooms_at else None)
    latest = [r for r in history if r.scanned_at == latest_at]
    return DayDetailOut(
        hotel=HotelOut.model_validate(hotel),
        stay_date=stay_date,
        room_types=[RoomTypeOut.model_validate(r) for r in room_types],
        latest_status=latest_status,
        latest_scanned_at=latest_at,
        latest=[RoomSnapshotOut.model_validate(r) for r in latest],
        history=[RoomSnapshotOut.model_validate(r) for r in history],
        observations=[HotelDateSnapshotOut.model_validate(o) for o in observations],
        events=events,
    )


@router.get("/events", response_model=list[EventOut])
async def list_events(
    tenant_id: TenantDep,
    session: SessionDep,
    hotel_id: int | None = None,
    event_type: str | None = None,
    stay_from: date | None = None,
    stay_to: date | None = None,
    observed_since: datetime | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> list[EventOut]:
    ids = await tenant_hotel_ids(session, tenant_id, include_inactive=True)
    if not ids:
        return []
    stmt = _events_stmt().where(AvailabilityEvent.hotel_id.in_(ids))
    if hotel_id is not None:
        if hotel_id not in ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not in watchlist")
        stmt = stmt.where(AvailabilityEvent.hotel_id == hotel_id)
    if event_type:
        stmt = stmt.where(AvailabilityEvent.event_type.in_(event_type.split(",")))
    if stay_from:
        stmt = stmt.where(AvailabilityEvent.stay_date >= stay_from)
    if stay_to:
        stmt = stmt.where(AvailabilityEvent.stay_date <= stay_to)
    if observed_since:
        stmt = stmt.where(AvailabilityEvent.observed_at >= observed_since)
    stmt = (
        stmt.order_by(AvailabilityEvent.observed_at.desc(), AvailabilityEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return await _events_out(session, stmt)


@router.get("/runs", response_model=list[ScanRunOut])
async def list_runs(
    tenant_id: TenantDep, session: SessionDep, limit: int = Query(10, ge=1, le=100)
) -> list[ScanRunOut]:
    return await _tenant_runs(session, tenant_id, limit=limit, finished_only=False)
