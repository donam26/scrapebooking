"""Lịch thị trường toàn thành phố, chạy trong mỗi tick của scheduler.

- Quét danh sách: từ `list_time` giờ địa phương của tenant, mỗi khu vực một vòng mỗi ngày (chốt bằng
  `market_areas.list_requested_at`, nên scheduler tắt lúc 03:00 thì lần chạy sau trong ngày vẫn bù);
  chuỗi đứng yên quá lâu thì được đẩy lại từ đêm chưa quét (app/marketscan/rounds.py).
- Quét chi tiết: từ `detail_time`, một run `market:<khu vực>:<YYYYMMDD>` (khoá duy nhất của
  scan_runs) cho top `detail_max_hotels` khách sạn của khu vực (nhiều review trước), horizon
  `detail_horizon_days`, chạy bằng probe worker với planner tầng sẵn có → analytics + công suất ước
  tính như mọi run.
- Đẩy dần: mỗi run thị trường chỉ giữ `inflight` job chờ trong hàng đợi kênh, tick sau bổ sung, để
  run thường của tenant không phải xếp sau hàng trăm khách sạn thị trường.
- Dọn dẹp: lượt quét một đêm kẹt "running" → lỗi; xoá lượt quét danh sách cũ (mỗi ngày một lần).

Mỗi khu vực xử lý trong session và try/except riêng: lỗi ở một khu vực không chặn khu vực khác.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Hotel, Listing, ScanJob, ScanRun, Tenant
from app.logging import get_logger
from app.marketscan.models import MarketArea, MarketAreaHotel
from app.marketscan.rounds import (
    ListQueue,
    fail_stuck_scans,
    market_pause_key,
    purge_old_scans,
    recover_round,
    start_round,
)
from app.repo.runs import MARKET_RUN_PREFIX, HotelJobPlan, ScanRunRepository
from app.scheduler.planning import safe_zone

log = get_logger(__name__)

SEEN_WINDOW = timedelta(days=14)  # khách sạn không còn trong danh sách 14 ngày: không quét chi tiết
IDLE_RETRY = timedelta(minutes=30)  # chưa có gì để quét chi tiết: thử lại sau
STUCK_EVERY = timedelta(minutes=15)


class MarketQueue(ListQueue, Protocol):
    async def enqueue_probe(self, scan_run_id: int, hotel_id: int, channel: str) -> None: ...


@dataclass
class MarketTickReport:
    list_enqueued: list[int] = field(default_factory=list)  # id khu vực
    recovered: list[int] = field(default_factory=list)  # id khu vực được đẩy lại chuỗi
    detail_runs: list[int] = field(default_factory=list)  # id run
    topped_up: int = 0
    failed_areas: list[int] = field(default_factory=list)


def market_trigger_key(area_id: int, day: date) -> str:
    return f"{MARKET_RUN_PREFIX}{area_id}:{day:%Y%m%d}"


def _at(day: date, hhmm: str, tz: ZoneInfo) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=tz).astimezone(UTC)


async def detail_candidates(s: AsyncSession, area: MarketArea, seen_since: datetime) -> list[int]:
    """Khách sạn của khu vực có listing kênh đang quét, nhiều review trước, rồi hạng danh sách."""
    rows = await s.execute(
        select(MarketAreaHotel.hotel_id)
        .join(Hotel, Hotel.id == MarketAreaHotel.hotel_id)
        .join(Listing, Listing.hotel_id == MarketAreaHotel.hotel_id)
        .where(
            MarketAreaHotel.area_id == area.id,
            MarketAreaHotel.last_seen_at >= seen_since,
            Listing.channel == area.channel,
            Listing.status == "active",
        )
        .order_by(
            Hotel.review_count.desc().nulls_last(),
            MarketAreaHotel.best_rank.asc().nulls_last(),
            MarketAreaHotel.hotel_id,
        )
    )
    return [r[0] for r in rows]


class MarketScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: MarketQueue,
        list_time: str = "03:00",
        detail_time: str = "05:00",
        inflight: int = 4,
        paused: Callable[[str], Awaitable[bool]] | None = None,
        max_hotels: int = 500,
        retention_days: int = 120,
    ) -> None:
        self._sf = session_factory
        self._queue = queue
        self._list_time = list_time
        self._detail_time = detail_time
        self._inflight = max(1, inflight)
        self._paused = paused
        self._max_hotels = max_hotels
        self._retention_days = retention_days
        self._idle_until: dict[int, datetime] = {}  # khu vực chưa có gì quét chi tiết
        self._stuck_checked_at: datetime | None = None
        self._purged_on: date | None = None

    async def _is_paused(self, key: str) -> bool:
        return self._paused is not None and await self._paused(key)

    async def tick(self, now: datetime) -> MarketTickReport:
        report = MarketTickReport()
        async with self._sf() as s:
            areas = (
                await s.execute(
                    select(MarketArea.id, Tenant.timezone)
                    .join(Tenant, Tenant.id == MarketArea.tenant_id)
                    .where(MarketArea.active.is_(True), Tenant.active.is_(True))
                    .order_by(MarketArea.id)
                )
            ).all()
        for area_id, tz_name in areas:
            tz = safe_zone(tz_name)
            if tz is None:
                continue
            try:
                async with self._sf() as s:
                    await self._area_tick(s, area_id, tz, now, report)
            except Exception:  # noqa: BLE001 — một khu vực lỗi không chặn khu vực khác
                log.exception("market_area_tick_failed", area_id=area_id)
                report.failed_areas.append(area_id)
        try:
            async with self._sf() as s:
                report.topped_up = await self._top_up(s)
                await self._housekeeping(s, now)
        except Exception:  # noqa: BLE001
            log.exception("market_top_up_failed")
        return report

    async def _area_tick(
        self, s: AsyncSession, area_id: int, tz: ZoneInfo, now: datetime, report: MarketTickReport
    ) -> None:
        area = await s.get(MarketArea, area_id)
        if area is None:
            return
        today = now.astimezone(tz).date()
        list_paused = await self._is_paused(area.channel) or await self._is_paused(
            market_pause_key(area.channel)
        )
        list_at = _at(today, self._list_time, tz)
        if not list_paused and now >= list_at:
            if await start_round(s, self._queue, area, now, list_at, today):
                report.list_enqueued.append(area.id)
                log.info("market_list_enqueued", area_id=area.id, trigger="daily")
            elif await recover_round(s, self._queue, area, tz, now) is not None:
                report.recovered.append(area.id)
        if (
            area.detail_max_hotels > 0
            and now >= _at(today, self._detail_time, tz)
            and not await self._is_paused(area.channel)
        ):
            run_id = await self._start_detail(s, area, today, tz, now)
            if run_id is not None:
                report.detail_runs.append(run_id)

    async def _start_detail(
        self, s: AsyncSession, area: MarketArea, today: date, tz: ZoneInfo, now: datetime
    ) -> int | None:
        # Đã tạo run hôm nay, hoặc vừa thấy không có gì để quét: không truy vấn lại mỗi tick.
        if area.last_detail_scan_at and area.last_detail_scan_at.astimezone(tz).date() == today:
            return None
        if now < self._idle_until.get(area.id, now):
            return None
        key = market_trigger_key(area.id, today)
        if (await s.execute(select(ScanRun.id).where(ScanRun.trigger_key == key))).first():
            return None
        candidates = await detail_candidates(s, area, now - SEEN_WINDOW)
        repo = ScanRunRepository(s)
        # Khách sạn đã có lượt quét trong ngày (run thường, khu vực khác trùng địa bàn): bỏ qua.
        midnight = datetime.combine(today, time(0), tzinfo=tz).astimezone(UTC)
        scanned = await repo.hotels_scanned_since(candidates, midnight, area.channel)
        limit = min(area.detail_max_hotels, self._max_hotels)
        chosen = [h for h in candidates if h not in scanned][:limit]
        if not chosen:
            self._idle_until[area.id] = now + IDLE_RETRY  # chưa có danh sách hoặc đã quét hết
            return None
        plans = [HotelJobPlan(h, today, area.detail_horizon_days) for h in chosen]
        run = await repo.create_run(key, now, plans, area.channel)
        if run is None:
            return None
        area.last_detail_scan_at, area.last_detail_run_id = now, run.id
        await s.commit()  # job được đẩy vào hàng đợi ở _top_up ngay trong tick này
        self._idle_until.pop(area.id, None)
        log.info("market_detail_run_created", area_id=area.id, run_id=run.id, jobs=len(plans))
        return run.id

    async def _top_up(self, s: AsyncSession) -> int:
        """Giữ tối đa `inflight` job chờ cho mỗi run thị trường đang chạy. Đẩy lại job đang chờ là
        vô hại: arq bỏ qua `_job_id` trùng (probe:<run>:<hotel>)."""
        runs = (
            await s.execute(
                select(ScanRun.id, ScanRun.channel).where(
                    ScanRun.status == "running",
                    ScanRun.trigger_key.startswith(MARKET_RUN_PREFIX),
                )
            )
        ).all()
        n = 0
        for run_id, channel in runs:
            if await self._is_paused(channel):
                continue
            rows = await s.execute(
                select(ScanJob.hotel_id)
                .join(Hotel, Hotel.id == ScanJob.hotel_id)
                .where(ScanJob.scan_run_id == run_id, ScanJob.status == "queued")
                .order_by(Hotel.review_count.desc().nulls_last(), ScanJob.hotel_id)
                .limit(self._inflight)
            )
            for (hotel_id,) in rows:
                await self._queue.enqueue_probe(run_id, hotel_id, channel)
                n += 1
        return n

    async def _housekeeping(self, s: AsyncSession, now: datetime) -> None:
        if self._stuck_checked_at is None or now - self._stuck_checked_at >= STUCK_EVERY:
            self._stuck_checked_at = now
            if stuck := await fail_stuck_scans(s, now):
                log.warning("market_list_scans_stuck", count=stuck)
        if self._purged_on != now.date():
            self._purged_on = now.date()
            if purged := await purge_old_scans(s, now, self._retention_days):
                log.info("market_list_scans_purged", count=purged)
