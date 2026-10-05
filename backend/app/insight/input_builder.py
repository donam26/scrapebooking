"""Gom JSON gọn cho AI (spec mục 8): bảng 30 ngày theo khách sạn, sự kiện 24h/7d, compset,
occupancy PMS, ngày lễ. Không HTML thô, không để AI tự tính delta.

Mỗi phần tử có `ref` để AI trích bằng chứng: `metric:<hotel_id>:<date>`, `evt:<id>`,
`compset:<date>`, `demand:<id>`.

Giới hạn đầu vào: tối đa `max_hotels` khách sạn (self trước, rồi đối thủ theo thứ tự
watchlist); `events_24h` và `events_7d` không trùng nhau (7d chỉ gồm sự kiện cũ hơn 24h).
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    ListingDemandSignal,
    OwnHotelDaily,
    RoomType,
    Tenant,
    TenantHotel,
)
from app.holidays.data import holidays_between, is_weekend
from app.i18n import normalize_locale

EVENT_LIMIT_24H = 120
EVENT_LIMIT_7D = 200
# Bản tin phục vụ quyết định buổi sáng: tối đa 30 đêm dù horizon quét là 90 (giữ đầu vào gọn).
INSIGHT_MAX_DAYS = 30
INSIGHT_MAX_HOTELS = 25

PRIORITY_EVENTS = (
    "channel_closed",
    "parity_gap",
    "sold_out",
    "restock",
    "low_stock_enter",
    "price_down",
    "price_up",
    "rooms_decrease",
)
# Sự kiện giá chỉ lấy mức khách sạn (room_type_id NULL): giá từng loại phòng lặp lại cùng
# biến động và làm đầu vào phình.
HOTEL_LEVEL_ONLY = ("price_down", "price_up")


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
    session: AsyncSession,
    tenant: Tenant,
    now: datetime | None = None,
    max_hotels: int = INSIGHT_MAX_HOTELS,
) -> InsightInput:
    now = now or datetime.now(tz=UTC)
    tz = ZoneInfo(tenant.timezone)
    today = now.astimezone(tz).date()
    days_n = min(tenant.horizon_days, INSIGHT_MAX_DAYS)
    start, end = today, today + timedelta(days=days_n - 1)
    channel = tenant.reference_channel

    # role desc: "self" trước "competitor"; trong mỗi vai theo thứ tự thêm vào watchlist.
    all_links = (
        await session.execute(
            select(TenantHotel, Hotel)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant.id, TenantHotel.active.is_(True))
            .order_by(TenantHotel.role.desc(), TenantHotel.added_at, TenantHotel.hotel_id)
        )
    ).all()
    links = all_links[: max(max_hotels, 1)]
    hotels_omitted = len(all_links) - len(links)
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
        "reference_channel": channel,
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days_n},
        "hotels": [],
        "events_24h": [],
        "events_7d": [],
        "compset": [],
        "demand_signals": [],
        "holidays": [
            {"date": h.date.isoformat(), "name": h.name}
            for h in holidays_between(
                tenant.country_code,
                start,
                end + timedelta(days=7),
                normalize_locale(tenant.insight_language),
            )
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
                    HotelDateMetric.channel == channel,
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
        for i in range(days_n):
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
                "name": hotel.name or f"#{hotel.id}",
                "label": link.label,
                "role": link.role,
                "days": days,
            }
        )

    async def _events(since: datetime, until: datetime | None, limit: int) -> list[dict[str, Any]]:
        """Sự kiện ưu tiên quan sát từ `since` (tới trước `until` nếu có)."""
        stmt = (
            select(AvailabilityEvent, Hotel.name, RoomType.name)
            .join(Hotel, Hotel.id == AvailabilityEvent.hotel_id)
            .outerjoin(RoomType, RoomType.id == AvailabilityEvent.room_type_id)
            .where(
                AvailabilityEvent.hotel_id.in_(hotel_ids),
                AvailabilityEvent.observed_at >= since,
                AvailabilityEvent.stay_date >= start,
                AvailabilityEvent.stay_date <= end,
                AvailabilityEvent.event_type.in_(PRIORITY_EVENTS),
                or_(
                    AvailabilityEvent.event_type.not_in(HOTEL_LEVEL_ONLY),
                    AvailabilityEvent.room_type_id.is_(None),
                ),
            )
            .order_by(AvailabilityEvent.observed_at.desc(), AvailabilityEvent.id.desc())
            .limit(limit)
        )
        if until is not None:
            stmt = stmt.where(AvailabilityEvent.observed_at < until)
        rows = (await session.execute(stmt)).all()
        out = []
        for e, hotel_name, rt_name in rows:
            ref = f"evt:{e.id}"
            refs.add(ref)
            out.append(
                {
                    "ref": ref,
                    "hotel_id": e.hotel_id,
                    "hotel": hotel_name,
                    "channel": e.channel,
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

    # Hai cửa sổ rời nhau: 24h gần nhất, và 7 ngày trước đó trừ 24h (không gửi sự kiện 2 lần).
    cutoff_24h = now - timedelta(hours=24)
    payload["events_24h"] = await _events(cutoff_24h, None, EVENT_LIMIT_24H)
    payload["events_7d"] = await _events(now - timedelta(days=7), cutoff_24h, EVENT_LIMIT_7D)

    signals = (
        (
            await session.execute(
                select(ListingDemandSignal)
                .where(
                    ListingDemandSignal.hotel_id.in_(hotel_ids),
                    ListingDemandSignal.observed_at >= now - timedelta(days=2),
                )
                .order_by(ListingDemandSignal.observed_at.desc())
            )
        )
        .scalars()
        .all()
    )
    seen: set[tuple[int, str, str, date | None]] = set()
    for sig in signals:
        key = (sig.hotel_id, sig.channel, sig.kind, sig.stay_date)
        if key in seen:
            continue  # chỉ giữ giá trị mới nhất mỗi (khách sạn, kênh, loại, đêm)
        seen.add(key)
        ref = f"demand:{sig.id}"
        refs.add(ref)
        payload["demand_signals"].append(
            {
                "ref": ref,
                "hotel_id": sig.hotel_id,
                "channel": sig.channel,
                "kind": sig.kind,
                "value": _num(sig.value),
                "window_hours": sig.window_hours,
                "stay_date": sig.stay_date.isoformat() if sig.stay_date else None,
                "text": sig.raw_text,
            }
        )

    for c in await compset_by_day(session, tenant.id, start, end, channel=channel):
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
                HotelDateSnapshot.hotel_id.in_(hotel_ids), HotelDateSnapshot.channel == channel
            )
        )
    ).scalar_one()
    payload["data_quality"] = {
        "hotel_dates_observed": observed,
        "hotel_dates_unknown": unknown,
        "unknown_rate": round(unknown_rate, 3) if unknown_rate is not None else None,
        "last_observation_at": last_obs.isoformat() if last_obs else None,
        "has_pms_data": bool(own_daily),
        "hotels_omitted": hotels_omitted,
    }
    return InsightInput(payload, refs, set(hotel_ids), start, end, scan_run_id)
