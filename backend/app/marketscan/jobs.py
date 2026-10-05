"""Job arq `scan_market_list` trên hàng đợi của kênh (đăng ký trong app/worker/settings.py, một lần
thử: chuỗi tự lo việc đi tiếp).

Mỗi job quét một đêm (một request; đêm khám phá thêm các lát bộ lọc × thứ tự) rồi đẩy job đêm kế
tiếp vào cuối hàng đợi, nên job probe của các lượt quét thường xen vào giữa thay vì chờ cả lượt
danh sách. Đêm lỗi (mạng, lỗi nội bộ) thì bỏ qua sang đêm sau; bị chặn thì dừng chuỗi và tạm dừng
quét danh sách của kênh (`market_pause_key`) để "Quét ngay" không gửi tiếp vào chỗ đang chặn.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Tenant
from app.logging import get_logger
from app.marketscan.models import MarketArea
from app.marketscan.rounds import MAX_LIST_NIGHTS, market_pause_key, round_ts
from app.marketscan.service import AreaTarget, MarketListService
from app.scheduler.planning import safe_zone

log = get_logger(__name__)


def local_today(timezone: str, now: datetime) -> date:
    return now.astimezone(safe_zone(timezone) or UTC).date()


def discovery_index(list_nights: int) -> int:
    """Đêm khám phá của vòng (số ngày kể từ đêm đầu): mặc định đêm thứ 8, khi phòng còn nhiều nhất
    (đêm gần đã vơi, đêm xa nhiều khách sạn chưa mở bán); vòng ngắn hơn thì đêm cuối."""
    return max(0, min(get_settings().market_discovery_night, list_nights - 1))


async def _set_area(
    sf: async_sessionmaker[AsyncSession],
    area_id: int,
    status: str,
    error: str | None,
    now: datetime,
) -> None:
    async with sf() as s:
        await s.execute(
            update(MarketArea)
            .where(MarketArea.id == area_id)
            .values(last_list_scan_at=now, last_list_status=status, last_list_error=error)
        )
        await s.commit()


async def scan_market_list(
    ctx: dict[str, Any],
    area_id: int,
    start: str | None = None,
    index: int = 0,
    round_id: int | None = None,
) -> str:
    deps = ctx["deps"]
    sf: async_sessionmaker[AsyncSession] = deps.session_factory
    collector, channel = ctx["collector"], ctx["channel"]
    if not hasattr(collector, "search_page"):
        return "unsupported"
    async with sf() as s:
        row = (
            await s.execute(
                select(MarketArea, Tenant.timezone)
                .join(Tenant, Tenant.id == MarketArea.tenant_id)
                .where(MarketArea.id == area_id)
            )
        ).first()
    if row is None:
        return "missing"
    area, timezone = row
    if not area.active or area.channel != channel:
        return "inactive"
    requested = area.list_requested_at
    current_round = round_ts(requested) if requested is not None else None
    if round_id is not None and round_id != current_round:
        return "superseded"  # đã có vòng mới: chuỗi cũ dừng, không chạy chồng
    now = deps.clock.now()
    pauses = ctx["pauses"]
    if await pauses.is_paused(channel) or await pauses.is_paused(market_pause_key(channel)):
        await _set_area(sf, area_id, "paused", "paused", now)
        return "paused"
    settings = get_settings()
    nights = min(area.list_nights, MAX_LIST_NIGHTS)
    first = date.fromisoformat(start) if start else local_today(timezone, now)
    if index >= nights:
        return "done"
    svc = MarketListService(
        sf, collector, deps.clock, currency=settings.scan_currency, adults=deps.default_adults
    )
    target = AreaTarget(
        area_id=area.id,
        channel=area.channel,
        dest_id=area.dest_id,
        dest_type=area.dest_type,
        max_requests=min(area.max_pages, settings.market_max_pages),
        round_started=requested or now - timedelta(hours=1),
    )
    result = await svc.scan_night(
        target, first + timedelta(days=index), discover=index == discovery_index(nights)
    )
    if result.status == "blocked":
        await pauses.pause(
            market_pause_key(channel), settings.channel_pause_minutes, "market list blocked"
        )
        await _set_area(sf, area_id, "blocked", result.error, deps.clock.now())
        log.warning("market_list_stopped", area_id=area_id, index=index, error=result.error)
        return "blocked"
    last = index + 1 >= nights
    # Lỗi của đêm này (nếu có) được giữ tới hết vòng để giao diện thấy; đêm đầu vòng thì xoá lỗi cũ.
    error = result.error or (area.last_list_error if index > 0 else None)
    await _set_area(sf, area_id, "completed" if last else "running", error, deps.clock.now())
    if not last:
        await ctx["queue"].enqueue_market_list(
            area_id, channel, first.isoformat(), index + 1, current_round
        )
    return result.status
