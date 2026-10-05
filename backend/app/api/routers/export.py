"""Tải CSV: bảng tổng quan (khách sạn × đêm + thị trường) và dòng sự kiện, cùng bộ lọc màn hình."""

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
    channel: str | None = None,
) -> Response:
    data = await overview(tenant_id, session, start, end, price_basis, channel, locale)
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
    channel: str | None = None,
) -> Response:
    events = await list_events(
        tenant_id,
        session,
        hotel_id=hotel_id,
        event_type=event_type,
        stay_from=stay_from,
        stay_to=stay_to,
        observed_since=observed_since,
        channel=channel,
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
