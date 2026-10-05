"""Vòng quét danh sách của khu vực: chốt yêu cầu (idempotent, trả lại khi không đẩy được job), mã
job theo vòng, bù chuỗi bị đứt, dọn lượt quét kẹt, xoá dữ liệu cũ. Dùng chung cho scheduler, job và
API "Quét ngay".

Một vòng = `list_requested_at` của khu vực: các đêm [ngày bắt đầu, + list_nights), mỗi đêm một job
nối tiếp với `_job_id` cố định `mlist:<khu vực>:<vòng>:<đêm>` (đẩy trùng là vô hại). Vòng mới thay
vòng cũ: job của vòng cũ tự dừng ("superseded"), nên không có hai chuỗi chạy chồng nhau.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.marketscan.models import MarketArea, MarketListScan

log = get_logger(__name__)

MAX_LIST_NIGHTS = 30
STALE_CHAIN = timedelta(hours=2)  # chuỗi không tiến triển quá lâu (job mất, worker chết…): bù
STUCK_SCAN = timedelta(hours=2)  # lượt quét một đêm "running" quá lâu: coi là lỗi
RECOVER_STATUSES = ("queued", "running", "error", "paused")


class ListQueue(Protocol):
    async def enqueue_market_list(
        self,
        area_id: int,
        channel: str,
        start: str | None = None,
        index: int = 0,
        round_ts: int | None = None,
    ) -> None: ...


def market_pause_key(channel: str) -> str:
    """Khoá tạm dừng riêng của quét danh sách (trang danh sách bị chặn): không dừng probe."""
    return f"{channel}:market"


def round_ts(requested_at: datetime) -> int:
    return int(requested_at.timestamp())


@dataclass(frozen=True)
class Claim:
    area_id: int
    requested_at: datetime
    prev_requested_at: datetime | None
    prev_status: str | None
    prev_error: str | None


async def claim_list_scan(
    s: AsyncSession, area_id: int, now: datetime, since: datetime
) -> Claim | None:
    """Ghi yêu cầu quét danh sách (trạng thái "queued") nếu chưa có yêu cầu nào từ `since`. Khoá
    dòng khu vực: hai scheduler/hai lần bấm cùng lúc chỉ một bên thắng. Người gọi commit."""
    row = (
        await s.execute(
            select(
                MarketArea.list_requested_at,
                MarketArea.last_list_status,
                MarketArea.last_list_error,
            )
            .where(MarketArea.id == area_id)
            .with_for_update()
        )
    ).first()
    if row is None or (row[0] is not None and row[0] >= since):
        return None
    await s.execute(
        update(MarketArea)
        .where(MarketArea.id == area_id)
        .values(list_requested_at=now, last_list_status="queued", last_list_error=None)
    )
    return Claim(area_id, now, row[0], row[1], row[2])


async def release_claim(s: AsyncSession, claim: Claim) -> None:
    """Trả lại yêu cầu khi không đẩy được job (Redis lỗi): lần sau còn quét được trong ngày."""
    await s.execute(
        update(MarketArea)
        .where(MarketArea.id == claim.area_id, MarketArea.list_requested_at == claim.requested_at)
        .values(
            list_requested_at=claim.prev_requested_at,
            last_list_status=claim.prev_status,
            last_list_error=claim.prev_error,
        )
    )


async def start_round(
    s: AsyncSession,
    queue: ListQueue,
    area: MarketArea,
    now: datetime,
    since: datetime,
    start: date,
) -> bool:
    """Chốt vòng mới → commit → đẩy job đêm đầu. Đẩy lỗi thì trả lại chốt và ném lỗi tiếp."""
    claim = await claim_list_scan(s, area.id, now, since)
    await s.commit()
    if claim is None:
        return False
    try:
        await queue.enqueue_market_list(area.id, area.channel, start.isoformat(), 0, round_ts(now))
    except Exception:
        await release_claim(s, claim)
        await s.commit()
        raise
    return True


async def next_unscanned_index(
    s: AsyncSession, area_id: int, start: date, nights: int, since: datetime
) -> int | None:
    """Đêm đầu tiên của vòng (bắt đầu `start`) chưa có lượt quét nào từ `since`."""
    scanned = {
        d
        for (d,) in await s.execute(
            select(MarketListScan.stay_date)
            .where(MarketListScan.area_id == area_id, MarketListScan.scanned_at >= since)
            .distinct()
        )
    }
    for i in range(nights):
        if start + timedelta(days=i) not in scanned:
            return i
    return None


async def recover_round(
    s: AsyncSession, queue: ListQueue, area: MarketArea, tz: ZoneInfo, now: datetime
) -> int | None:
    """Chuỗi của vòng hôm nay đứng yên quá `STALE_CHAIN` (job mất, worker chết giữa chừng): đẩy lại
    từ đêm chưa quét đầu tiên. Trả chỉ số đêm đã đẩy (None nếu không cần)."""
    requested = area.list_requested_at
    if requested is None or area.last_list_status not in RECOVER_STATUSES:
        return None
    if requested.astimezone(tz).date() != now.astimezone(tz).date():
        return None
    if now - max(area.last_list_scan_at or requested, requested) < STALE_CHAIN:
        return None
    start = requested.astimezone(tz).date()
    nights = min(area.list_nights, MAX_LIST_NIGHTS)
    index = await next_unscanned_index(s, area.id, start, nights, requested)
    # Đặt lại mốc để tick sau không bù tiếp trong `STALE_CHAIN`.
    status = "queued" if index is not None else "completed"
    await s.execute(
        update(MarketArea)
        .where(MarketArea.id == area.id)
        .values(last_list_status=status, last_list_scan_at=now)
    )
    await s.commit()
    if index is None:
        return None
    await queue.enqueue_market_list(
        area.id, area.channel, start.isoformat(), index, round_ts(requested)
    )
    log.warning("market_list_recovered", area_id=area.id, index=index)
    return index


async def fail_stuck_scans(s: AsyncSession, now: datetime) -> int:
    res = await s.execute(
        update(MarketListScan)
        .where(MarketListScan.status == "running", MarketListScan.scanned_at < now - STUCK_SCAN)
        .values(status="error", error="error: stuck", finished_at=now)
    )
    await s.commit()
    return int(getattr(res, "rowcount", 0) or 0)


async def purge_old_scans(s: AsyncSession, now: datetime, keep_days: int) -> int:
    """Xoá lượt quét danh sách (và giá, theo FK cascade) cũ hơn `keep_days` ngày."""
    res = await s.execute(
        delete(MarketListScan).where(MarketListScan.scanned_at < now - timedelta(days=keep_days))
    )
    await s.commit()
    return int(getattr(res, "rowcount", 0) or 0)
