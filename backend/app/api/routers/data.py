from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import PriceBasis, compset_by_day, metric_price
from app.analytics.cross_channel import TAX_INCLUSIVE_CHANNELS
from app.api.deps import (
    LocaleDep,
    PrincipalDep,
    SessionDep,
    TenantDep,
    ensure_hotel_in_tenant,
    tenant_hotel_ids,
)
from app.api.hotel_views import (
    hotel_out,
    hotel_outs,
    sort_channels,
    tenant_channel,
    tenant_channels,
)
from app.api.schemas import (
    ChannelDayOut,
    CompsetDayOut,
    DateCell,
    DayDetailOut,
    DemandSignalOut,
    EventOut,
    HolidayOut,
    HotelDateSnapshotOut,
    HotelDetailOut,
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
    ListingDemandSignal,
    Probe,
    RoomSnapshot,
    RoomType,
    ScanJob,
    ScanRun,
    Tenant,
    TenantHotel,
)
from app.domain.models import ProbeStatus
from app.holidays.data import holidays_between
from app.i18n import DEFAULT_LOCALE
from app.marketscan.models import MarketArea
from app.repo.runs import MARKET_RUN_PREFIX

router = APIRouter(tags=["data"])

MAX_RANGE_DAYS = 120


async def _horizon(session: AsyncSession, tenant_id: int) -> tuple[int, date]:
    """(số đêm quét tới, đêm xa nhất trong phạm vi quét = hôm nay giờ địa phương + horizon - 1)."""
    tenant = await session.get(Tenant, tenant_id)
    days = tenant.horizon_days if tenant else 1
    return days, await _local_today(session, tenant_id) + timedelta(days=days - 1)


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


def _cell(d: date, m: HotelDateMetric | None, basis: PriceBasis = PriceBasis.ANY) -> DateCell:
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
        min_price=metric_price(m, basis),
        currency=m.currency,
        pickup_24h=m.pickup_24h,
        velocity_3d=m.velocity_3d,
        price_change_7d_pct=m.price_change_7d_pct,
        exact_share=m.exact_share,
        sold_out_at=m.sold_out_at,
        restocked_at=m.restocked_at,
        last_observed_at=m.last_observed_at,
        days_to_arrival=m.days_to_arrival,
        stale_since=m.stale_since,
    )


async def _events_out(session: AsyncSession, stmt: Select[Any]) -> list[EventOut]:
    rows = (await session.execute(stmt)).all()
    return [
        EventOut(
            id=e.id,
            hotel_id=e.hotel_id,
            hotel_name=h.name,
            channel=e.channel,
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


def _visible_trigger_key(key: str, tenant_id: int, own_areas: set[int]) -> str:
    """Không lộ mã tenant/khu vực của tenant khác khi run dùng chung khách sạn: run thủ công của
    tenant khác → "manual", run thị trường của khu vực tenant khác → "market"."""
    if key.startswith("manual:t") and not key.startswith(f"manual:t{tenant_id}:"):
        return "manual"
    if key.startswith("market:"):
        area = key.split(":")[1]
        if not area.isdigit() or int(area) not in own_areas:
            return "market"
    return key


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
        # "Lượt quét gần nhất" của tenant là mốc quét compset, không phải run thị trường cả khu vực.
        stmt = stmt.where(~ScanRun.trigger_key.startswith(MARKET_RUN_PREFIX))
        stmt = stmt.where(ScanRun.status.in_(["completed", "partial"])).order_by(
            ScanRun.finished_at.desc()
        )
    else:
        stmt = stmt.order_by(ScanRun.id.desc())
    runs = list((await session.execute(stmt.limit(limit))).scalars())
    if not runs:
        return []
    run_ids = [r.id for r in runs]
    own_areas = set(
        (
            await session.execute(select(MarketArea.id).where(MarketArea.tenant_id == tenant_id))
        ).scalars()
    )
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
                channel=r.channel,
                trigger_key=_visible_trigger_key(r.trigger_key, tenant_id, own_areas),
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
    price_basis: PriceBasis = PriceBasis.ANY,
    channel: str | None = None,
    locale: LocaleDep = DEFAULT_LOCALE,
) -> OverviewOut:
    s, e = _range(start, end, await _local_today(session, tenant_id))
    ch = await tenant_channel(session, tenant_id, channel)
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
                    HotelDateMetric.channel == ch,
                    HotelDateMetric.stay_date >= s,
                    HotelDateMetric.stay_date <= e,
                )
            )
        ).scalars()
        metrics = {(m.hotel_id, m.stay_date): m for m in rows}
    days = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    outs = await hotel_outs(session, [h for _, h in links])
    hotels = [
        HotelRow(
            hotel=outs[h.id],
            role=link.role,
            label=link.label,
            cells=[_cell(d, metrics.get((h.id, d)), price_basis) for d in days],
        )
        for link, h in links
    ]
    compset = [
        CompsetDayOut(**c.__dict__)
        for c in await compset_by_day(session, tenant_id, s, e, price_basis, ch)
    ]
    last_runs = await _tenant_runs(session, tenant_id, limit=1, finished_only=True)
    return OverviewOut(
        start=s,
        end=e,
        channel=ch,
        channels=sort_channels([*await tenant_channels(session, tenant_id), ch]),
        horizon_end=(await _horizon(session, tenant_id))[1],
        hotels=hotels,
        compset=compset,
        holidays=await _holidays(session, tenant_id, s, e, locale),
        last_run=last_runs[0] if last_runs else None,
    )


async def _holidays(
    session: AsyncSession, tenant_id: int, start: date, end: date, locale: str
) -> list[HolidayOut]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return []
    return [
        HolidayOut(date=h.date, name=h.name, kind=h.kind, group=h.group)
        for h in holidays_between(tenant.country_code, start, end, locale)
    ]


@router.get("/hotels/{hotel_id}", response_model=HotelDetailOut)
async def hotel_detail(
    hotel_id: int,
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
    event_limit: int = Query(200, ge=1, le=1000),
    channel: str | None = None,
) -> HotelDetailOut:
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    s, e = _range(start, end, await _local_today(session, tenant_id))
    ch = await tenant_channel(session, tenant_id, channel)
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
                    HotelDateMetric.channel == ch,
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
        hotel=await hotel_out(session, hotel),
        role=link.role,
        label=link.label,
        channel=ch,
        demand_signals=await _demand_signals(session, hotel_id, None),
        horizon_end=(await _horizon(session, tenant_id))[1],
        metrics=[_cell(d, metrics.get(d)) for d in days],
        events=events,
    )


@router.get("/hotels/{hotel_id}/dates/{stay_date}", response_model=DayDetailOut)
async def day_detail(
    hotel_id: int,
    stay_date: date,
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    history_days: int = Query(14, ge=1, le=60),
    channel: str | None = None,
) -> DayDetailOut:
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not found")
    ch = await tenant_channel(session, tenant_id, channel)
    since = datetime.now(tz=UTC) - timedelta(days=history_days)
    history = list(
        (
            await session.execute(
                select(RoomSnapshot)
                .where(
                    RoomSnapshot.hotel_id == hotel_id,
                    RoomSnapshot.channel == ch,
                    RoomSnapshot.stay_date == stay_date,
                    RoomSnapshot.scanned_at >= since,
                )
                .order_by(RoomSnapshot.scanned_at, RoomSnapshot.room_type_id)
            )
        ).scalars()
    )
    observations = list(
        (
            await session.execute(
                select(HotelDateSnapshot)
                .where(
                    HotelDateSnapshot.hotel_id == hotel_id,
                    HotelDateSnapshot.channel == ch,
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
    # Lần quét gần nhất của đêm này, không phụ thuộc khoảng lịch sử đang xem (lâu không quét thì
    # vẫn thấy dữ liệu cuối cùng). Lấy theo quan sát (gồm cả hết phòng/không rõ, vốn không có
    # snapshot loại phòng); snapshot mới hơn quan sát nghĩa là analytics chưa chạy xong lần đó.
    last_obs = (
        await session.execute(
            select(HotelDateSnapshot)
            .where(
                HotelDateSnapshot.hotel_id == hotel_id,
                HotelDateSnapshot.channel == ch,
                HotelDateSnapshot.stay_date == stay_date,
            )
            .order_by(HotelDateSnapshot.scanned_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    rooms_at = (
        await session.execute(
            select(func.max(RoomSnapshot.scanned_at)).where(
                RoomSnapshot.hotel_id == hotel_id,
                RoomSnapshot.channel == ch,
                RoomSnapshot.stay_date == stay_date,
            )
        )
    ).scalar_one()
    latest_at: datetime | None
    latest_status: str | None
    if last_obs is not None and (rooms_at is None or last_obs.scanned_at >= rooms_at):
        latest_at, latest_status = last_obs.scanned_at, last_obs.status
    else:
        latest_at, latest_status = rooms_at, ("available" if rooms_at else None)
    latest = (
        list(
            (
                await session.execute(
                    select(RoomSnapshot)
                    .where(
                        RoomSnapshot.hotel_id == hotel_id,
                        RoomSnapshot.channel == ch,
                        RoomSnapshot.stay_date == stay_date,
                        RoomSnapshot.scanned_at == latest_at,
                    )
                    .order_by(RoomSnapshot.room_type_id)
                )
            ).scalars()
        )
        if latest_at is not None
        else []
    )
    rt_ids = {r.room_type_id for r in history} | {r.room_type_id for r in latest}
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
    # Lượt quét gần nhất của khách sạn (mọi đêm) và đêm xa nhất nó phủ: giải thích vì sao một đêm
    # chưa có dữ liệu (ngoài phạm vi quét, hay chưa có lượt quét nào kể từ khi đêm vào phạm vi).
    # hotel_date_metrics: một dòng mỗi đêm, giữ lượt quét mới nhất của đêm đó (bảng nhỏ, có cận).
    last_scan = (
        await session.execute(
            select(HotelDateMetric.as_of_scan_run_id, HotelDateMetric.last_observed_at)
            .where(HotelDateMetric.hotel_id == hotel_id, HotelDateMetric.channel == ch)
            .order_by(HotelDateMetric.last_observed_at.desc())
            .limit(1)
        )
    ).first()
    last_scan_through = (
        (
            await session.execute(
                select(func.max(HotelDateMetric.stay_date)).where(
                    HotelDateMetric.hotel_id == hotel_id,
                    HotelDateMetric.channel == ch,
                    HotelDateMetric.as_of_scan_run_id == last_scan[0],
                )
            )
        ).scalar_one()
        if last_scan
        else None
    )
    horizon_days, horizon_end = await _horizon(session, tenant_id)
    day_compset = await compset_by_day(session, tenant_id, stay_date, stay_date, PriceBasis.ANY, ch)
    day_holidays = await _holidays(session, tenant_id, stay_date, stay_date, locale)
    channel_rows = (
        await session.execute(
            select(HotelDateMetric).where(
                HotelDateMetric.hotel_id == hotel_id, HotelDateMetric.stay_date == stay_date
            )
        )
    ).scalars()
    by_channel = {m.channel: m for m in channel_rows}
    label = (
        await session.execute(
            select(TenantHotel.label).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id
            )
        )
    ).scalar_one_or_none()
    return DayDetailOut(
        hotel=await hotel_out(session, hotel),
        label=label,
        stay_date=stay_date,
        channel=ch,
        channels=[
            ChannelDayOut(
                channel=c,
                availability_status=by_channel[c].availability_status,
                exact_rooms_left=by_channel[c].exact_rooms_left,
                min_price=by_channel[c].min_price,
                min_refundable_price=by_channel[c].min_refundable_price,
                currency=by_channel[c].currency,
                last_observed_at=by_channel[c].last_observed_at,
                tax_inclusive=c in TAX_INCLUSIVE_CHANNELS,
            )
            for c in sort_channels(by_channel)
        ],
        demand_signals=await _demand_signals(session, hotel_id, stay_date),
        room_types=[RoomTypeOut.model_validate(r) for r in room_types],
        latest_status=latest_status,
        latest_scanned_at=latest_at,
        latest=[RoomSnapshotOut.model_validate(r) for r in latest],
        horizon_days=horizon_days,
        horizon_end=horizon_end,
        last_scan_at=last_scan[1] if last_scan else None,
        last_scan_through=last_scan_through,
        history=[RoomSnapshotOut.model_validate(r) for r in history],
        observations=[HotelDateSnapshotOut.model_validate(o) for o in observations],
        events=events,
        compset=CompsetDayOut(**day_compset[0].__dict__) if day_compset else None,
        holiday=day_holidays[0].name if day_holidays else None,
        holiday_kind=day_holidays[0].kind if day_holidays else None,
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
    channel: str | None = None,
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
    if channel:
        stmt = stmt.where(AvailabilityEvent.channel.in_(channel.split(",")))
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


class RunJobOut(BaseModel):
    """Job của một khách sạn trong một lượt quét (chỉ khách sạn thuộc tenant)."""

    hotel_id: int
    hotel_name: str | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    total_probes: int
    ok_count: int
    sold_out_count: int
    blocked_count: int
    error_count: int
    # Lỗi kỹ thuật (proxy, deadline…): chỉ operator thấy.
    error: str | None = None


@router.get("/runs/{run_id}/jobs", response_model=list[RunJobOut])
async def list_run_jobs(
    run_id: int, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> list[RunJobOut]:
    """Từng khách sạn của tenant trong lượt quét: trạng thái job, số lượt đọc trang theo kết quả."""
    hotel_ids = await tenant_hotel_ids(session, tenant_id, include_inactive=True)
    if not hotel_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    labels: dict[int, str | None] = {
        int(row[0]): row[1]
        for row in (
            await session.execute(
                select(TenantHotel.hotel_id, func.coalesce(TenantHotel.label, Hotel.name))
                .join(Hotel, Hotel.id == TenantHotel.hotel_id)
                .where(TenantHotel.tenant_id == tenant_id)
            )
        ).all()
    }
    jobs = list(
        (
            await session.execute(
                select(ScanJob)
                .where(ScanJob.scan_run_id == run_id, ScanJob.hotel_id.in_(hotel_ids))
                .order_by(ScanJob.hotel_id)
            )
        ).scalars()
    )
    if not jobs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    probes: dict[int, dict[str, int]] = {}
    for hotel_id, status_, n in await session.execute(
        select(Probe.hotel_id, Probe.status, func.count())
        .where(Probe.scan_run_id == run_id, Probe.hotel_id.in_(hotel_ids))
        .group_by(Probe.hotel_id, Probe.status)
    ):
        probes.setdefault(hotel_id, {})[status_] = n
    out = []
    for j in jobs:
        by = probes.get(j.hotel_id, {})
        out.append(
            RunJobOut(
                hotel_id=j.hotel_id,
                hotel_name=labels.get(j.hotel_id),
                status=j.status,
                started_at=j.started_at,
                finished_at=j.finished_at,
                total_probes=sum(by.values()),
                ok_count=by.get(str(ProbeStatus.OK), 0),
                sold_out_count=by.get(str(ProbeStatus.SOLD_OUT), 0)
                + by.get(str(ProbeStatus.SKIPPED_CALENDAR), 0),
                blocked_count=by.get(str(ProbeStatus.BLOCKED), 0),
                error_count=by.get(str(ProbeStatus.ERROR), 0),
                error=j.error if principal.is_operator else None,
            )
        )
    return out


async def _demand_signals(
    session: AsyncSession, hotel_id: int, stay_date: date | None, days: int = 7
) -> list[DemandSignalOut]:
    """Tín hiệu cầu mới nhất mỗi (kênh, loại) trong `days` ngày: cả khách sạn, và của đêm nếu có."""
    since = datetime.now(tz=UTC) - timedelta(days=days)
    cond: ColumnElement[bool] = ListingDemandSignal.stay_date.is_(None)
    if stay_date is not None:
        cond = or_(cond, ListingDemandSignal.stay_date == stay_date)
    rows = (
        await session.execute(
            select(ListingDemandSignal)
            .where(
                ListingDemandSignal.hotel_id == hotel_id,
                ListingDemandSignal.observed_at >= since,
                cond,
            )
            .order_by(ListingDemandSignal.observed_at.desc())
        )
    ).scalars()
    latest: dict[tuple[str, str, date | None], ListingDemandSignal] = {}
    for r in rows:
        latest.setdefault((r.channel, r.kind, r.stay_date), r)
    return [DemandSignalOut.model_validate(r) for r in latest.values()]
