from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.repo.runs import HotelJobPlan


@dataclass(frozen=True)
class TenantSchedule:
    id: int
    timezone: str
    scan_times: tuple[str, ...]
    horizon_days: int


@dataclass(frozen=True)
class Trigger:
    key: str
    at: datetime
    tenant_ids: tuple[int, ...]


@dataclass(frozen=True)
class WatchRow:
    tenant_id: int
    hotel_id: int
    horizon_days: int
    timezone: str


def trigger_key(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def compute_triggers(
    tenants: Iterable[TenantSchedule], now: datetime, lookback: timedelta
) -> list[Trigger]:
    """Mốc giờ quét của mọi tenant rơi vào (now - lookback, now], gom theo phút UTC."""
    buckets: dict[str, tuple[datetime, set[int]]] = {}
    for tenant in tenants:
        tz = ZoneInfo(tenant.timezone)
        local_today = now.astimezone(tz).date()
        for day_offset in (0, -1):
            local_date = local_today + timedelta(days=day_offset)
            for scan_time in tenant.scan_times:
                hh, mm = (int(x) for x in scan_time.split(":"))
                at = datetime.combine(local_date, time(hh, mm), tzinfo=tz).astimezone(UTC)
                if now - lookback < at <= now:
                    key = trigger_key(at)
                    buckets.setdefault(key, (at, set()))[1].add(tenant.id)
    return sorted(
        (Trigger(key, at, tuple(sorted(ids))) for key, (at, ids) in buckets.items()),
        key=lambda t: t.at,
    )


def build_hotel_plans(rows: Iterable[WatchRow], trigger_at: datetime) -> list[HotelJobPlan]:
    """Một job mỗi khách sạn: start_date là ngày địa phương sớm nhất, horizon là lớn nhất."""
    per_hotel: dict[int, tuple[date, int]] = {}
    for row in rows:
        local_date = trigger_at.astimezone(ZoneInfo(row.timezone)).date()
        current = per_hotel.get(row.hotel_id)
        if current is None:
            per_hotel[row.hotel_id] = (local_date, row.horizon_days)
        else:
            per_hotel[row.hotel_id] = (
                min(current[0], local_date),
                max(current[1], row.horizon_days),
            )
    return [HotelJobPlan(h, d, n) for h, (d, n) in sorted(per_hotel.items())]
