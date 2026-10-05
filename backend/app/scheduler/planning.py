from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.logging import get_logger
from app.repo.runs import HotelJobPlan

log = get_logger(__name__)


def safe_zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.error("invalid_timezone", timezone=name)
        return None


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
    channel: str = "booking"  # một dòng mỗi listing đang quét (khách sạn × kênh)


def trigger_key(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def channel_trigger_key(key: str, channel: str) -> str:
    """Mỗi mốc giờ một run cho mỗi kênh (D9): kênh chậm/bị chặn không kéo trễ kênh khác."""
    return f"{key}:{channel}"


def rows_by_channel(rows: Iterable[WatchRow]) -> dict[str, list[WatchRow]]:
    out: dict[str, list[WatchRow]] = {}
    for row in rows:
        out.setdefault(row.channel, []).append(row)
    return dict(sorted(out.items()))


def _slots(tenant: TenantSchedule, now: datetime) -> list[datetime]:
    """Mốc quét (UTC) của tenant trong hôm nay và hôm qua theo giờ địa phương."""
    tz = safe_zone(tenant.timezone)
    if tz is None:
        return []
    local_today = now.astimezone(tz).date()
    out: list[datetime] = []
    for day_offset in (0, -1):
        local_date = local_today + timedelta(days=day_offset)
        for scan_time in tenant.scan_times:
            hh, mm = (int(x) for x in scan_time.split(":"))
            out.append(datetime.combine(local_date, time(hh, mm), tzinfo=tz).astimezone(UTC))
    return out


def compute_triggers(
    tenants: Iterable[TenantSchedule], now: datetime, lookback: timedelta
) -> list[Trigger]:
    """Mốc giờ quét của mọi tenant rơi vào (now - lookback, now], gom theo phút UTC."""
    buckets: dict[str, tuple[datetime, set[int]]] = {}
    for tenant in tenants:
        for at in _slots(tenant, now):
            if now - lookback < at <= now:
                buckets.setdefault(trigger_key(at), (at, set()))[1].add(tenant.id)
    return sorted(
        (Trigger(key, at, tuple(sorted(ids))) for key, (at, ids) in buckets.items()),
        key=lambda t: t.at,
    )


def missed_slots(
    tenants: Iterable[TenantSchedule], now: datetime, lookback: timedelta
) -> dict[int, datetime]:
    """tenant_id -> mốc quét gần nhất của tenant, với tenant mà mốc đó đã ra khỏi cửa sổ
    (now - lookback, now] của `compute_triggers`. Sau một quãng scheduler không chạy, đây là mốc
    có thể đã bị lỡ; mốc cũ hơn không cần bù vì mốc gần nhất đã thay thế."""
    out: dict[int, datetime] = {}
    for tenant in tenants:
        latest = max((at for at in _slots(tenant, now) if at <= now), default=None)
        if latest is not None and latest <= now - lookback:
            out[tenant.id] = latest
    return out


def build_hotel_plans(rows: Iterable[WatchRow], trigger_at: datetime) -> list[HotelJobPlan]:
    """Một job mỗi khách sạn: start_date là ngày địa phương sớm nhất, horizon là lớn nhất."""
    per_hotel: dict[int, tuple[date, int]] = {}
    for row in rows:
        tz = safe_zone(row.timezone) or UTC
        local_date = trigger_at.astimezone(tz).date()
        current = per_hotel.get(row.hotel_id)
        if current is None:
            per_hotel[row.hotel_id] = (local_date, row.horizon_days)
        else:
            per_hotel[row.hotel_id] = (
                min(current[0], local_date),
                max(current[1], row.horizon_days),
            )
    return [HotelJobPlan(h, d, n) for h, (d, n) in sorted(per_hotel.items())]
