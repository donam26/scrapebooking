"""Điều kiện cảnh báo vận hành (roadmap 0.4) và số liệu độ tin cậy dữ liệu theo kênh (0.6, 0.7).

Hàm thuần (`*_alerts`, `success_rate`) có test; phần đọc DB nằm ở `channel_probe_stats` và
`channel_last_success`. Thành công = trang đã đọc được (còn phòng, hết phòng, lịch báo không bán,
chưa có phòng 1 đêm); thất bại = bị chặn hoặc lỗi.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, Probe, Tenant, TenantHotel
from app.domain.models import ProbeStatus

FAILED_STATUSES = (str(ProbeStatus.BLOCKED), str(ProbeStatus.ERROR))
# Quan sát có dữ liệu dùng được (giá/tồn phòng hoặc trạng thái hết phòng chắc chắn).
DATA_STATUSES = (
    str(ProbeStatus.OK),
    str(ProbeStatus.SOLD_OUT),
    str(ProbeStatus.SKIPPED_CALENDAR),
)

SUCCESS_RATE_MIN = 0.8  # tỷ lệ thành công 24h dưới mức này thì báo operator
SUCCESS_RATE_MIN_PROBES = 30
STALE_AFTER = timedelta(hours=10)  # 3 lượt/ngày cách 8h + biên: một chu kỳ quét không có dữ liệu


@dataclass(frozen=True)
class ChannelStats:
    channel: str
    total: int
    failed: int
    with_data: int

    @property
    def success_rate(self) -> float | None:
        return (self.total - self.failed) / self.total if self.total else None


def success_rate_alerts(
    stats: Iterable[ChannelStats],
    threshold: float = SUCCESS_RATE_MIN,
    min_probes: int = SUCCESS_RATE_MIN_PROBES,
) -> list[tuple[str, str]]:
    """(kênh, câu cảnh báo) cho kênh có tỷ lệ thành công 24h dưới ngưỡng (đủ mẫu)."""
    out = []
    for s in stats:
        rate = s.success_rate
        if rate is None or s.total < min_probes or rate >= threshold:
            continue
        out.append(
            (
                s.channel,
                f"⚠️ [{s.channel}] success rate {rate:.0%} in 24h "
                f"({s.total - s.failed}/{s.total} probes; target ≥{threshold:.0%})",
            )
        )
    return out


def stale_channel_alerts(
    active_channels: Iterable[str],
    last_success: dict[str, datetime],
    now: datetime,
    stale_after: timedelta = STALE_AFTER,
) -> list[tuple[str, str]]:
    """(kênh, câu cảnh báo): kênh đang có listing quét mà không có dữ liệu mới quá `stale_after`."""
    out = []
    for ch in sorted(set(active_channels)):
        last = last_success.get(ch)
        if last is not None and now - last <= stale_after:
            continue
        since = f"since {last.strftime('%Y-%m-%d %H:%M UTC')}" if last else "ever"
        out.append((ch, f"⚠️ [{ch}] no usable data {since} (> {stale_after} without data)"))
    return out


def stale_after_hours(scan_times: list[str]) -> int:
    """Một chu kỳ quét: khoảng cách lớn nhất giữa hai mốc quét liên tiếp (vòng 24h) + 2 giờ biên
    (run chạy tối đa 90 phút). 06:00/14:00/22:00 → 10 giờ; một mốc/ngày → 26 giờ."""
    mins = sorted(
        {int(t[:2]) * 60 + int(t[3:5]) for t in scan_times if len(t) >= 5 and t[2] == ":"}
    )
    if not mins:
        return 26
    gaps = [(b - a) for a, b in zip(mins, [*mins[1:], mins[0] + 24 * 60], strict=True)]
    return max(gaps) // 60 + 2


def expired_runs_alert(run_ids: list[int]) -> str | None:
    if not run_ids:
        return None
    ids = ", ".join(f"#{r}" for r in run_ids[:10])
    more = f" (+{len(run_ids) - 10})" if len(run_ids) > 10 else ""
    return f"⚠️ Scan runs overdue and force-closed at deadline: {ids}{more}"


async def channel_probe_stats(
    s: AsyncSession, since: datetime, hotel_ids: list[int] | None = None
) -> dict[str, ChannelStats]:
    """Số probe theo kênh kể từ `since` (bỏ probe "lịch báo không bán": không gửi request)."""
    stmt = select(Probe.channel, Probe.status, func.count()).where(Probe.fetched_at >= since)
    if hotel_ids is not None:
        if not hotel_ids:
            return {}
        stmt = stmt.where(Probe.hotel_id.in_(hotel_ids))
    stmt = stmt.group_by(Probe.channel, Probe.status)
    acc: dict[str, list[int]] = {}
    for channel, status, n in await s.execute(stmt):
        row = acc.setdefault(channel, [0, 0, 0])
        if status == str(ProbeStatus.SKIPPED_CALENDAR):
            row[2] += n  # có dữ liệu (đêm không bán) nhưng không tính vào tỷ lệ request
            continue
        row[0] += n
        if status in FAILED_STATUSES:
            row[1] += n
        if status in DATA_STATUSES:
            row[2] += n
    return {ch: ChannelStats(ch, t, f, d) for ch, (t, f, d) in acc.items()}


async def channel_last_success(
    s: AsyncSession, hotel_ids: list[int] | None = None, since: datetime | None = None
) -> dict[str, datetime]:
    """Quan sát có dữ liệu gần nhất theo kênh (không phải lượt quét kết thúc gần nhất)."""
    stmt = select(Probe.channel, func.max(Probe.fetched_at)).where(Probe.status.in_(DATA_STATUSES))
    if since is not None:
        stmt = stmt.where(Probe.fetched_at >= since)
    if hotel_ids is not None:
        if not hotel_ids:
            return {}
        stmt = stmt.where(Probe.hotel_id.in_(hotel_ids))
    rows = await s.execute(stmt.group_by(Probe.channel))
    return {ch: at for ch, at in rows if at is not None}


async def active_listing_channels(s: AsyncSession) -> set[str]:
    """Kênh có ít nhất một listing đang quét của một tenant đang hoạt động."""
    rows = await s.execute(
        select(Listing.channel)
        .distinct()
        .join(TenantHotel, TenantHotel.hotel_id == Listing.hotel_id)
        .join(Tenant, Tenant.id == TenantHotel.tenant_id)
        .where(
            Listing.status == "active",
            TenantHotel.active.is_(True),
            Tenant.active.is_(True),
        )
    )
    return {r[0] for r in rows}
