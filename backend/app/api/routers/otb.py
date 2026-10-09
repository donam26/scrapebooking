"""OTB của khách sạn của bạn (roadmap Phase 5): nhập báo cáo OTB theo ngày hoặc file đặt phòng
chi tiết; pickup 1/7 ngày, pace so 4 tuần trước và STLY, dự báo cộng pickup; KPI thật (Occ, ADR,
RevPAR) — nửa còn lại của quyết định giá."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.analytics.compset import compset_by_day, load_compset
from app.api.deps import SessionDep, TenantDep, WriterDep, ensure_hotel_in_tenant
from app.db.models import OwnHotelDaily, PmsImport, Tenant, TenantHotel
from app.market.models import OtbSnapshot
from app.market.pace_report import tenant_today
from app.pms.base import ImportSummary, PmsAdapterError
from app.pms.csv_adapter import CsvAdapter
from app.pms.otb import (
    OtbRow,
    build_curves,
    kpis,
    otb_night,
    parse_bookings,
    parse_otb_report,
    rebuild_snapshots,
    suggest_booking_mapping,
    suggest_otb_mapping,
)

router = APIRouter(tags=["otb"])

OtbKind = Literal["otb_report", "bookings"]
HISTORY_DAYS = 400  # đủ cho STLY (364 ngày) + dự báo


class OtbImportOut(BaseModel):
    kind: str
    hotel_id: int
    rows_read: int
    snapshots_written: int
    as_of_dates: int
    stay_dates: int
    errors: list[dict[str, object]]
    status: str


class OtbNightOut(BaseModel):
    stay_date: date
    lead: int
    rooms_otb: int | None
    revenue_otb: Decimal | None
    rooms_available: int | None
    occ_otb_pct: Decimal | None
    adr_otb: Decimal | None
    pickup_1d: int | None
    pickup_7d: int | None
    pace_4w: int | None
    ref_4w: int | None
    stly: int | None
    pace_stly: int | None
    forecast_rooms: int | None
    forecast_occ_pct: Decimal | None
    forecast_basis: int


class KpiOut(BaseModel):
    nights: int
    rooms_sold: int
    rooms_available: int
    revenue: Decimal
    occupancy_pct: Decimal | None
    adr: Decimal | None
    revpar: Decimal | None


class OtbOut(BaseModel):
    hotel_id: int | None
    as_of_date: date | None  # bản chụp OTB mới nhất
    start: date
    end: date
    nights: list[OtbNightOut]
    # KPI thật 30 đêm đã qua (PMS) và OTB các đêm sắp tới.
    actual_30d: KpiOut
    otb_window: KpiOut
    # Chỉ số giá niêm yết của bạn trong khoảng (trung vị các đêm đủ mẫu) và số đêm đủ mẫu (n/N).
    price_index_median: Decimal | None
    price_index_nights: int


def _template(kind: OtbKind) -> str:
    if kind == "bookings":
        return (
            "booking_date,arrival,departure,rooms,revenue,status,cancel_date,group\n"
            "2026-09-01,2026-10-17,2026-10-19,1,3600000,confirmed,,\n"
            "2026-09-05,2026-10-17,2026-10-18,2,3800000,cancelled,2026-09-20,\n"
            "2026-09-10,2026-10-24,2026-10-26,10,30000000,confirmed,,yes\n"
        )
    return (
        "as_of_date,stay_date,rooms_otb,revenue_otb,rooms_available,cancellations,group_rooms\n"
        "2026-10-09,2026-10-17,42,79800000,120,3,10\n"
        "2026-10-09,2026-10-18,35,64400000,120,1,0\n"
    )


@router.get("/pms/otb/template", response_class=PlainTextResponse)
async def otb_template(_: TenantDep, kind: OtbKind = "otb_report") -> str:
    return _template(kind)


@router.post("/pms/otb/import", response_model=OtbImportOut, status_code=status.HTTP_201_CREATED)
async def import_otb(
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    hotel_id: Annotated[int, Form()],
    kind: Annotated[OtbKind, Form()] = "otb_report",
    as_of_date: Annotated[date | None, Form()] = None,
    rooms_available: Annotated[int | None, Form()] = None,
) -> OtbImportOut:
    """Nhập OTB không ghi đè ngày khác: (khách sạn, ngày chụp, đêm) là khoá. File đặt phòng dựng
    lại bản chụp cho cả quá khứ (pace/STLY có ngay)."""
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    link = (
        await session.execute(
            select(TenantHotel).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id
            )
        )
    ).scalar_one()
    if link.role != "self":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "OTB only for role=self hotel")
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    today = tenant_today(tenant)
    filename = file.filename or "upload"
    try:
        table = CsvAdapter().read_table(await file.read(), filename)
    except PmsAdapterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    rows: list[OtbRow]
    if kind == "bookings":
        bookings, errors = parse_bookings(table, suggest_booking_mapping(table.columns))
        rows = rebuild_snapshots(bookings, today, rooms_available)
        ok = len(bookings)
    else:
        rows, errors = parse_otb_report(
            table, suggest_otb_mapping(table.columns), as_of_date or today
        )
        ok = len(rows)
    now = datetime.now(tz=UTC)
    for r in rows:
        values = dict(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            as_of_date=r.as_of_date,
            stay_date=r.stay_date,
            rooms_otb=r.rooms_otb,
            revenue_otb=r.revenue_otb,
            rooms_available=r.rooms_available or rooms_available,
            cancellations=r.cancellations,
            group_rooms=r.group_rooms,
            source=kind,
            imported_at=now,
        )
        await session.execute(
            insert(OtbSnapshot)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    OtbSnapshot.tenant_id,
                    OtbSnapshot.hotel_id,
                    OtbSnapshot.as_of_date,
                    OtbSnapshot.stay_date,
                ],
                set_={
                    k: v
                    for k, v in values.items()
                    if k not in ("tenant_id", "hotel_id", "as_of_date", "stay_date")
                },
            )
        )
    summary = ImportSummary(row_count=len(table.rows), ok_count=ok, errors=errors)
    session.add(
        PmsImport(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            filename=filename[:255],
            adapter=kind,
            row_count=summary.row_count,
            ok_count=summary.ok_count,
            errors=[e.__dict__ for e in errors[:200]],
            status=summary.status,
        )
    )
    await session.commit()
    return OtbImportOut(
        kind=kind,
        hotel_id=hotel_id,
        rows_read=len(table.rows),
        snapshots_written=len(rows),
        as_of_dates=len({r.as_of_date for r in rows}),
        stay_dates=len({r.stay_date for r in rows}),
        errors=[e.__dict__ for e in errors[:50]],
        status=summary.status,
    )


def _kpi_out(k: object) -> KpiOut:
    return KpiOut(**k.__dict__)


@router.get("/market/otb", response_model=OtbOut)
async def otb_view(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
    own_hotel_id: int | None = None,
    days: int = Query(30, ge=1, le=120),
) -> OtbOut:
    """OTB, pickup, pace (4 tuần trước, STLY) và dự báo theo đêm của khách sạn của bạn."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    today = tenant_today(tenant)
    s = start or today
    e = end or s + timedelta(days=days - 1)
    if e < s or (e - s).days > 120:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "range must be 1–120 nights")
    w = await load_compset(session, tenant_id, own_hotel_id)
    hid = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    empty = kpis([])
    if hid is None:
        return OtbOut(
            hotel_id=None,
            as_of_date=None,
            start=s,
            end=e,
            nights=[],
            actual_30d=_kpi_out(empty),
            otb_window=_kpi_out(empty),
            price_index_median=None,
            price_index_nights=0,
        )
    snaps = list(
        (
            await session.execute(
                select(OtbSnapshot).where(
                    OtbSnapshot.tenant_id == tenant_id,
                    OtbSnapshot.hotel_id == hid,
                    OtbSnapshot.stay_date >= s - timedelta(days=HISTORY_DAYS),
                    OtbSnapshot.stay_date <= e,
                )
            )
        ).scalars()
    )
    curves = build_curves((r.as_of_date, r.stay_date, r.rooms_otb) for r in snaps)
    latest: dict[date, OtbSnapshot] = {}
    for r in snaps:
        if r.as_of_date <= today and (
            r.stay_date not in latest or r.as_of_date > latest[r.stay_date].as_of_date
        ):
            latest[r.stay_date] = r
    as_of = max((r.as_of_date for r in snaps if r.as_of_date <= today), default=None)
    out_nights = []
    window_rows = []
    d = s
    while d <= e:
        cap = latest[d].rooms_available if d in latest else None
        n = otb_night(curves, d, today, cap)
        snap = latest.get(d)
        rev = snap.revenue_otb if snap else None
        occ = (
            (Decimal(n.rooms_otb) / cap * 100).quantize(Decimal("0.1"))
            if n.rooms_otb is not None and cap
            else None
        )
        out_nights.append(
            OtbNightOut(
                stay_date=d,
                lead=n.lead,
                rooms_otb=n.rooms_otb,
                revenue_otb=rev,
                rooms_available=cap,
                occ_otb_pct=occ,
                adr_otb=(rev / n.rooms_otb).quantize(Decimal("0.01"))
                if rev is not None and n.rooms_otb
                else None,
                pickup_1d=n.pickup_1d,
                pickup_7d=n.pickup_7d,
                pace_4w=n.pace_4w,
                ref_4w=n.ref_4w,
                stly=n.stly,
                pace_stly=n.pace_stly,
                forecast_rooms=n.forecast_rooms,
                forecast_occ_pct=(Decimal(n.forecast_rooms) / cap * 100).quantize(Decimal("0.1"))
                if n.forecast_rooms is not None and cap
                else None,
                forecast_basis=n.forecast_basis,
            )
        )
        window_rows.append((n.rooms_otb, cap, rev))
        d += timedelta(days=1)
    past = (
        await session.execute(
            select(
                OwnHotelDaily.rooms_sold,
                OwnHotelDaily.rooms_available,
                OwnHotelDaily.revenue,
                OwnHotelDaily.rooms_total,
            ).where(
                OwnHotelDaily.tenant_id == tenant_id,
                OwnHotelDaily.hotel_id == hid,
                OwnHotelDaily.stay_date >= today - timedelta(days=30),
                OwnHotelDaily.stay_date < today,
            )
        )
    ).all()
    # Phòng sẵn có của đêm = tổng phòng (hoặc bán + còn trống khi file không có tổng).
    actual = kpis(
        (sold, total or ((sold or 0) + avail if avail is not None else None), rev)
        for sold, avail, rev, total in past
    )
    comp = await compset_by_day(session, tenant_id, s, e, own_hotel_id=hid)
    idx = sorted(c.price_index for c in comp if c.price_index is not None and c.sample == "ok")
    med = idx[len(idx) // 2] if idx else None
    return OtbOut(
        hotel_id=hid,
        as_of_date=as_of,
        start=s,
        end=e,
        nights=out_nights,
        actual_30d=_kpi_out(actual),
        otb_window=_kpi_out(kpis(window_rows)),
        price_index_median=med,
        price_index_nights=len(idx),
    )
