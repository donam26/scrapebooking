"""Tải về: CSV tổng quan (khách sạn × đêm + compset) và dòng thay đổi; Excel "rate shop"; báo cáo
tháng cho chủ đầu tư (roadmap 7.4)."""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import PriceBasis
from app.api.deps import LocaleDep, SessionDep, TenantDep
from app.api.routers.data import list_events, overview
from app.db.models import Tenant, TenantHotel
from app.export.csv_tables import (
    events_header,
    events_rows,
    filename,
    overview_header,
    overview_rows,
    to_csv,
    truncated_row,
)
from app.export.reports import rate_shop_xlsx

router = APIRouter(prefix="/export", tags=["export"])

MAX_EXPORT_EVENTS = 2000
CSV_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"text/csv": {}}, "description": "Tệp CSV (UTF-8 có BOM)"}
}


async def _labels(session: AsyncSession, tenant_id: int) -> dict[int, str]:
    rows = await session.execute(
        select(TenantHotel.hotel_id, TenantHotel.label).where(TenantHotel.tenant_id == tenant_id)
    )
    return {r[0]: r[1] for r in rows if r[1]}


def _csv(body: str, name: str) -> Response:
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/overview.csv", response_class=Response, responses=CSV_RESPONSE)
async def export_overview(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    start: date | None = None,
    end: date | None = None,
    price_basis: PriceBasis = PriceBasis.ANY,
) -> Response:
    data = await overview(tenant_id, session, start, end, price_basis, locale=locale)
    rows = overview_rows(data, await _labels(session, tenant_id), locale)
    return _csv(to_csv(overview_header(locale), rows), filename("overview", data.start, locale))


@router.get("/events.csv", response_class=Response, responses=CSV_RESPONSE)
async def export_events(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    hotel_id: int | None = None,
    event_type: str | None = None,
    stay_from: date | None = None,
    stay_to: date | None = None,
    observed_since: datetime | None = None,
) -> Response:
    events = await list_events(
        tenant_id,
        session,
        hotel_id=hotel_id,
        event_type=event_type,
        stay_from=stay_from,
        stay_to=stay_to,
        observed_since=observed_since,
        limit=MAX_EXPORT_EVENTS + 1,
        offset=0,
    )
    truncated = len(events) > MAX_EXPORT_EVENTS
    tenant = await session.get(Tenant, tenant_id)
    try:
        tz = ZoneInfo(tenant.timezone if tenant else "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    rows = events_rows(events[:MAX_EXPORT_EVENTS], await _labels(session, tenant_id), tz, locale)
    if truncated:
        # Không để người dùng tưởng đã đủ: dòng cuối nói rõ và cách lấy phần còn lại.
        rows.append(truncated_row(MAX_EXPORT_EVENTS, locale))
    today = datetime.now(tz=tz).date()
    return _csv(to_csv(events_header(locale), rows), filename("events", today, locale))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/rate-shop.xlsx",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Excel rate shop"}},
)
async def export_rate_shop(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    start: date | None = None,
    end: date | None = None,
    price_basis: PriceBasis = PriceBasis.ANY,
) -> Response:
    """Excel "rate shop" đúng mẫu khách sạn ghi tay (7.4): khách sạn × đêm, compset, thay đổi."""
    data = await overview(tenant_id, session, start, end, price_basis, locale=locale)
    events = await list_events(
        tenant_id,
        session,
        stay_from=data.start,
        stay_to=data.end,
        event_type=(
            "sold_out,restock,price_up,price_down,lowest_rate_shift,restricted,"
            "restriction_lifted,min_stay_change,promo_start,promo_end"
        ),
        limit=MAX_EXPORT_EVENTS,
        offset=0,
    )
    body = rate_shop_xlsx(data, events, locale)
    name = filename("rate-shop", data.start, locale).replace(".csv", ".xlsx")
    return Response(
        content=body,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/monthly-report.html", response_class=Response)
async def export_monthly_report(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    month: str | None = None,
    own_hotel_id: int | None = None,
) -> Response:
    """Báo cáo tháng cho chủ đầu tư (HTML in thành PDF): KPI thật, vị trí giá, quyết định giá."""
    from datetime import timedelta

    from fastapi import HTTPException, status
    from sqlalchemy import func

    from app.analytics.compset import compset_by_day, load_compset
    from app.api.routers.market import suggestion_outcomes
    from app.db.models import AvailabilityEvent, Hotel, OwnHotelDaily
    from app.export.reports import MonthlyReport, monthly_report_html
    from app.market.pace_report import tenant_today
    from app.pms.otb import kpis

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    today = tenant_today(tenant)
    try:
        first = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "month must be YYYY-MM") from exc
    nxt = (first + timedelta(days=32)).replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    w = await load_compset(session, tenant_id, own_hotel_id)
    hid = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    if hid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no own hotel (role=self) in watchlist")
    hotel = await session.get(Hotel, hid)

    async def month_kpis(a: date, b: date) -> Any:
        rows = await session.execute(
            select(
                OwnHotelDaily.rooms_sold,
                OwnHotelDaily.rooms_total,
                OwnHotelDaily.rooms_available,
                OwnHotelDaily.revenue,
            ).where(
                OwnHotelDaily.tenant_id == tenant_id,
                OwnHotelDaily.hotel_id == hid,
                OwnHotelDaily.stay_date >= a,
                OwnHotelDaily.stay_date < b,
            )
        )
        return kpis(
            (sold, total or ((sold or 0) + avail if avail is not None else None), rev)
            for sold, total, avail, rev in rows
        )

    comp = await compset_by_day(
        session,
        tenant_id,
        first,
        nxt - timedelta(days=1),
        own_hotel_id=hid,
    )
    idx = sorted(c.price_index for c in comp if c.price_index is not None and c.sample == "ok")
    outcomes = await suggestion_outcomes(tenant_id, session, days=62, own_hotel_id=hid)
    highlights: list[str] = []
    if w.competitors:
        rows = await session.execute(
            select(Hotel.name, AvailabilityEvent.event_type, func.count())
            .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
            .where(
                AvailabilityEvent.hotel_id.in_(w.competitors),
                AvailabilityEvent.stay_date >= first,
                AvailabilityEvent.stay_date < nxt,
                AvailabilityEvent.event_type.in_(
                    ["sold_out", "promo_start", "price_up", "price_down"]
                ),
            )
            .group_by(Hotel.name, AvailabilityEvent.event_type)
            .order_by(func.count().desc())
            .limit(6)
        )
        for name, et, n in rows:
            highlights.append(f"{name}: {et} × {n}")
    report = MonthlyReport(
        tenant_name=tenant.name,
        hotel_name=(hotel.name if hotel else None) or f"#{hid}",
        month=first,
        kpis=await month_kpis(first, nxt),
        kpis_prev=await month_kpis(prev, first),
        index_median=idx[len(idx) // 2] if idx else None,
        index_nights=len(idx),
        outcomes=outcomes,
        highlights=highlights,
    )
    return Response(
        content=monthly_report_html(report, locale), media_type="text/html; charset=utf-8"
    )
