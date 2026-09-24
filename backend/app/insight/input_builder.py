"""Gom JSON gọn cho AI (spec mục 8): bảng 30 ngày theo khách sạn, sự kiện 24h/7d, compset,
occupancy PMS, ngày lễ. Không HTML thô, không để AI tự tính delta.

Mỗi phần tử có `ref` để AI trích bằng chứng: `metric:<hotel_id>:<date>`, `evt:<id>`,
`compset:<date>`.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    OwnHotelDaily,
    RoomType,
    Tenant,
    TenantHotel,
)
from app.holidays.data import holidays_between, is_weekend

EVENT_LIMIT_24H = 120
EVENT_LIMIT_7D = 200
PRIORITY_EVENTS = (
    "sold_out",
    "restock",
    "low_stock_enter",
    "price_down",
    "price_up",
    "rooms_decrease",
)


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


@dataclass
class InsightInput:
    payload: dict[str, Any]
    valid_refs: set[str] = field(default_factory=set)
    hotel_ids: set[int] = field(default_factory=set)
    period_start: date = date.min
    period_end: date = date.min
    scan_run_id: int | None = None


async def build_input(
    session: AsyncSession, tenant: Tenant, now: datetime | None = None
) -> InsightInput:
    now = now or datetime.now(tz=UTC)
    tz = ZoneInfo(tenant.timezone)
    today = now.astimezone(tz).date()
    start, end = today, today + timedelta(days=tenant.horizon_days - 1)

    links = (
        await session.execute(
            select(TenantHotel, Hotel)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant.id, TenantHotel.active.is_(True))
            .order_by(TenantHotel.role.desc(), TenantHotel.added_at)
        )
    ).all()
    hotel_ids = [h.id for _, h in links]
    refs: set[str] = set()
    payload: dict[str, Any] = {
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "timezone": tenant.timezone,
            "country": tenant.country_code,
        },
        "language": tenant.insight_language,
        "generated_at": now.isoformat(),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": tenant.horizon_days},
        "hotels": [],
        "events_24h": [],
        "events_7d": [],
        "compset": [],
        "holidays": [
            {"date": h.date.isoformat(), "name": h.name}
            for h in holidays_between(tenant.country_code, start, end + timedelta(days=7))
        ],
        "data_quality": {},
    }
    if not hotel_ids:
        return InsightInput(payload, refs, set(), start, end, None)

    metrics = (
        (
            await session.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id.in_(hotel_ids),
                    HotelDateMetric.stay_date >= start,
                    HotelDateMetric.stay_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    by_hotel: dict[int, dict[date, HotelDateMetric]] = {}
    for metric in metrics:
        by_hotel.setdefault(metric.hotel_id, {})[metric.stay_date] = metric
    scan_run_id = max((metric.as_of_scan_run_id for metric in metrics), default=None)

    own_ids = [h.id for link, h in links if link.role == "self"]
    own_daily: dict[tuple[int, date], OwnHotelDaily] = {}
    if own_ids:
        rows = (
            (
                await session.execute(
                    select(OwnHotelDaily).where(
                        OwnHotelDaily.tenant_id == tenant.id,
                        OwnHotelDaily.hotel_id.in_(own_ids),
                        OwnHotelDaily.stay_date >= start,
                        OwnHotelDaily.stay_date <= end,
                    )
                )
            )
            .scalars()
            .all()
        )
        own_daily = {(r.hotel_id, r.stay_date): r for r in rows}

    unknown = observed = 0
    for link, hotel in links:
        days = []
        for i in range(tenant.horizon_days):
            d = start + timedelta(days=i)
            m: HotelDateMetric | None = by_hotel.get(hotel.id, {}).get(d)
            ref = f"metric:{hotel.id}:{d.isoformat()}"
            if m is None:
                days.append({"date": d.isoformat(), "ref": ref, "status": "no_data"})
                continue
            refs.add(ref)
            observed += 1
            if m.availability_status == "unknown":
                unknown += 1
            row: dict[str, Any] = {
                "date": d.isoformat(),
                "ref": ref,
                "weekend": is_weekend(d),
                "status": m.availability_status,
                "rooms_left_exact": m.exact_rooms_left,
                "exact_share_7d": _num(m.exact_share),
                "min_price": _num(m.min_price),
                "currency": m.currency,
                "price_change_7d_pct": _num(m.price_change_7d_pct),
                "pickup_24h": m.pickup_24h,
                "velocity_3d": _num(m.velocity_3d),
                "sold_out_at": m.sold_out_at.isoformat() if m.sold_out_at else None,
                "restocked_at": m.restocked_at.isoformat() if m.restocked_at else None,
                "days_to_arrival": m.days_to_arrival,
            }
            pms = own_daily.get((hotel.id, d))
            if pms is not None:
                row["pms"] = {
                    "occupancy_pct": _num(pms.occupancy_pct),
                    "rooms_available": pms.rooms_available,
                    "rooms_sold": pms.rooms_sold,
                    "adr": _num(pms.adr),
                }
            days.append(row)
        payload["hotels"].append(
            {
                "hotel_id": hotel.id,
                "name": hotel.name or hotel.booking_slug,
                "label": link.label,
                "role": link.role,
                "days": days,
            }
        )

    async def _events(since: datetime, limit: int) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(AvailabilityEvent, Hotel.name, RoomType.name)
                .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
                .outerjoin(RoomType, RoomType.id == AvailabilityEvent.room_type_id)
                .where(
                    AvailabilityEvent.hotel_id.in_(hotel_ids),
                    AvailabilityEvent.observed_at >= since,
                    AvailabilityEvent.stay_date >= start,
                    AvailabilityEvent.stay_date <= end,
                    AvailabilityEvent.event_type.in_(PRIORITY_EVENTS),
                )
                .order_by(AvailabilityEvent.observed_at.desc(), AvailabilityEvent.id.desc())
                .limit(limit)
            )
        ).all()
        out = []
        for e, hotel_name, rt_name in rows:
            ref = f"evt:{e.id}"
            refs.add(ref)
            out.append(
                {
                    "ref": ref,
                    "hotel_id": e.hotel_id,
                    "hotel": hotel_name,
                    "room_type": rt_name,
                    "stay_date": e.stay_date.isoformat(),
                    "type": e.event_type,
                    "from": e.from_value,
                    "to": e.to_value,
                    "delta": _num(e.delta),
                    "confidence": e.confidence,
                    "observed_at": e.observed_at.isoformat(),
                }
            )
        return out

    payload["events_24h"] = await _events(now - timedelta(hours=24), EVENT_LIMIT_24H)
    payload["events_7d"] = await _events(now - timedelta(days=7), EVENT_LIMIT_7D)

    for c in await compset_by_day(session, tenant.id, start, end):
        ref = f"compset:{c.stay_date.isoformat()}"
        refs.add(ref)
        payload["compset"].append(
            {
                "date": c.stay_date.isoformat(),
                "ref": ref,
                "competitors_observed": c.competitors_observed,
                "competitors_sold_out": c.competitors_sold_out,
                "sold_out_share": _num(c.sold_out_share),
                "min_price": _num(c.min_price),
                "median_price": _num(c.median_price),
                "currency": c.currency,
                "own_min_price": _num(c.own_min_price),
                "own_status": c.own_status,
                "own_occupancy_pct": _num(c.own_occupancy_pct),
                "price_index": _num(c.price_index),
            }
        )

    unknown_rate = (unknown / observed) if observed else None
    last_obs = (
        await session.execute(
            select(func.max(HotelDateSnapshot.scanned_at)).where(
                HotelDateSnapshot.hotel_id.in_(hotel_ids)
            )
        )
    ).scalar_one()
    payload["data_quality"] = {
        "hotel_dates_observed": observed,
        "hotel_dates_unknown": unknown,
        "unknown_rate": round(unknown_rate, 3) if unknown_rate is not None else None,
        "last_observation_at": last_obs.isoformat() if last_obs else None,
        "has_pms_data": bool(own_daily),
    }
    return InsightInput(payload, refs, set(hotel_ids), start, end, scan_run_id)
