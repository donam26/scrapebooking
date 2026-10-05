from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Listing, Probe, ScanJob, ScanRun
from app.domain.models import ListingRef, ProbeStatus

# Trạng thái job chưa kết thúc. "retrying": lần thử trước lỗi, arq sẽ chạy lại (Retry defer).
PENDING_JOB_STATUSES = ("queued", "running", "retrying")
# Run quét chi tiết thị trường toàn thành phố (app/marketscan/scheduling.py): job được đẩy dần vào
# hàng đợi (không đẩy lại hàng loạt như job "queued" quá hạn) và có hạn chót riêng, dài hơn.
MARKET_RUN_PREFIX = "market:"


@dataclass(frozen=True)
class HotelJobPlan:
    hotel_id: int
    start_date: date
    horizon_days: int


class ScanRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_run(
        self,
        trigger_key: str,
        scheduled_at: datetime,
        plans: list[HotelJobPlan],
        channel: str = "booking",
    ) -> ScanRun | None:
        """Tạo run (một kênh) và job. Trả None nếu trigger_key đã tồn tại (đã tạo trước đó)."""
        existing = await self._s.execute(
            select(ScanRun.id).where(ScanRun.trigger_key == trigger_key)
        )
        if existing.first() is not None:
            return None
        run = ScanRun(
            trigger_key=trigger_key,
            scheduled_at=scheduled_at,
            started_at=scheduled_at,
            status="running",
            total_jobs=len(plans),
            channel=channel,
        )
        self._s.add(run)
        try:
            await self._s.flush()
        except IntegrityError:
            await self._s.rollback()
            return None
        for p in plans:
            self._s.add(
                ScanJob(
                    scan_run_id=run.id,
                    hotel_id=p.hotel_id,
                    start_date=p.start_date,
                    horizon_days=p.horizon_days,
                    status="queued",
                )
            )
        await self._s.flush()
        return run

    async def load_listing(self, hotel_id: int, channel: str) -> ListingRef | None:
        """Listing đang quét (active) của khách sạn trên kênh; None nếu đã bị xoá/tạm dừng/hỏng sau
        khi run được tạo (job phải chốt ngay, không để run chờ tới hạn chót)."""
        row = (
            await self._s.execute(
                select(Listing, Hotel.country_code)
                .join(Hotel, Hotel.id == Listing.hotel_id)
                .where(
                    Listing.hotel_id == hotel_id,
                    Listing.channel == channel,
                    Listing.status == "active",
                )
            )
        ).first()
        if row is None:
            return None
        listing, country_code = row
        return ListingRef(
            hotel_id=hotel_id,
            channel=channel,
            listing_key=listing.listing_key,
            url=listing.url,
            country_code=country_code,
            external_id=listing.external_id,
        )

    async def run_channel(self, scan_run_id: int) -> str:
        return str(
            (
                await self._s.execute(select(ScanRun.channel).where(ScanRun.id == scan_run_id))
            ).scalar_one()
        )

    async def start_job(self, scan_run_id: int, hotel_id: int, now: datetime) -> ScanJob | None:
        """Chuyển job sang running. Trả None nếu job đã done hoặc run đã chốt (retry arq tới muộn
        sau hạn chót): chạy lại không làm gì."""
        row = (
            await self._s.execute(
                select(ScanJob, ScanRun.status)
                .join(ScanRun, ScanRun.id == ScanJob.scan_run_id)
                .where(ScanJob.scan_run_id == scan_run_id, ScanJob.hotel_id == hotel_id)
            )
        ).first()
        if row is None:
            return None
        job: ScanJob = row[0]
        if job.status == "done" or row[1] != "running":
            return None
        job.status = "running"
        job.started_at = job.started_at or now
        job.error = None
        await self._s.flush()
        return job

    async def finish_job(
        self, scan_run_id: int, hotel_id: int, status: str, now: datetime, error: str | None = None
    ) -> None:
        await self._s.execute(
            update(ScanJob)
            .where(ScanJob.scan_run_id == scan_run_id, ScanJob.hotel_id == hotel_id)
            .values(status=status, finished_at=now, error=error)
        )
        await self._s.flush()

    async def try_finish_run(self, scan_run_id: int, now: datetime) -> bool:
        # Khoá dòng run: hai job cuối xong cùng lúc thì transaction sau chờ transaction trước commit
        # rồi mới đếm, nên luôn có một bên thấy hết job đã xong và chốt run.
        locked = await self._s.execute(
            select(ScanRun.status).where(ScanRun.id == scan_run_id).with_for_update()
        )
        if locked.scalar_one_or_none() != "running":
            return False
        pending = await self._s.execute(
            select(func.count())
            .select_from(ScanJob)
            .where(ScanJob.scan_run_id == scan_run_id, ScanJob.status.in_(PENDING_JOB_STATUSES))
        )
        if pending.scalar_one() > 0:
            return False
        failed = await self._s.execute(
            select(func.count())
            .select_from(ScanJob)
            .where(ScanJob.scan_run_id == scan_run_id, ScanJob.status == "failed")
        )
        counts = await self._s.execute(
            select(Probe.status, func.count())
            .where(Probe.scan_run_id == scan_run_id)
            .group_by(Probe.status)
        )
        by_status = {row[0]: row[1] for row in counts}
        # Chỉ chốt run đang chạy: job về sau (hoặc chạy lại) không chốt lần hai, không đẩy trùng
        # analytics/cảnh báo.
        result = await self._s.execute(
            update(ScanRun)
            .where(ScanRun.id == scan_run_id, ScanRun.status == "running")
            .values(
                status="partial" if failed.scalar_one() > 0 else "completed",
                finished_at=now,
                total_probes=sum(by_status.values()),
                ok_count=by_status.get(str(ProbeStatus.OK), 0),
                sold_out_count=by_status.get(str(ProbeStatus.SOLD_OUT), 0)
                + by_status.get(str(ProbeStatus.SKIPPED_CALENDAR), 0),
                blocked_count=by_status.get(str(ProbeStatus.BLOCKED), 0),
                error_count=by_status.get(str(ProbeStatus.ERROR), 0),
            )
        )
        await self._s.flush()
        return bool(getattr(result, "rowcount", 0))

    async def expire_runs(
        self, deadline: timedelta, now: datetime, market_deadline: timedelta | None = None
    ) -> list[int]:
        is_market = ScanRun.trigger_key.startswith(MARKET_RUN_PREFIX)
        overdue = ScanRun.started_at < now - deadline
        if market_deadline is not None:
            overdue = or_(
                and_(~is_market, overdue),
                and_(is_market, ScanRun.started_at < now - market_deadline),
            )
        rows = await self._s.execute(select(ScanRun.id).where(ScanRun.status == "running", overdue))
        expired = [r[0] for r in rows]
        for run_id in expired:
            await self._s.execute(
                update(ScanJob)
                .where(ScanJob.scan_run_id == run_id, ScanJob.status.in_(PENDING_JOB_STATUSES))
                .values(status="failed", finished_at=now, error="deadline")
            )
            await self.try_finish_run(run_id, now)
        return expired

    async def get_run(self, scan_run_id: int) -> ScanRun:
        return (
            await self._s.execute(select(ScanRun).where(ScanRun.id == scan_run_id))
        ).scalar_one()

    async def probe_stats_since(self, since: datetime) -> dict[str, tuple[int, int]]:
        """kênh -> (tổng probe có request thật, số bị chặn) kể từ `since`."""
        rows = await self._s.execute(
            select(Probe.channel, Probe.status, func.count())
            .where(Probe.fetched_at >= since, Probe.status != str(ProbeStatus.SKIPPED_CALENDAR))
            .group_by(Probe.channel, Probe.status)
        )
        out: dict[str, tuple[int, int]] = {}
        for channel, status, n in rows:
            total, blocked = out.get(channel, (0, 0))
            out[channel] = (total + n, blocked + (n if status == str(ProbeStatus.BLOCKED) else 0))
        return out

    async def stale_queued_jobs(self, queued_before: datetime) -> list[tuple[int, int, str]]:
        """(run, hotel, kênh) của job vẫn 'queued' trong run đang chạy được tạo trước
        `queued_before`: cần đẩy lại hàng đợi của kênh."""
        rows = await self._s.execute(
            select(ScanJob.scan_run_id, ScanJob.hotel_id, ScanRun.channel)
            .join(ScanRun, ScanRun.id == ScanJob.scan_run_id)
            .where(
                ScanJob.status == "queued",
                ScanRun.status == "running",
                ScanRun.started_at < queued_before,
                ~ScanRun.trigger_key.startswith(MARKET_RUN_PREFIX),
            )
        )
        return [(r[0], r[1], r[2]) for r in rows]

    async def hotels_scanned_since(
        self, hotel_ids: list[int], since: datetime, channel: str = "booking"
    ) -> set[int]:
        """Khách sạn (trong `hotel_ids`) có job chưa thất bại (đã xong, hoặc còn chờ trong run đang
        chạy) trong một run bắt đầu từ `since` trở đi. Job thất bại (proxy lỗi, run chết quá hạn
        chót…) không tính: khách sạn đó chưa có dữ liệu mới. Gọi sau `expire_runs` để job dở của
        run quá hạn đã bị chốt là thất bại."""
        if not hotel_ids:
            return set()
        rows = await self._s.execute(
            select(ScanJob.hotel_id)
            .distinct()
            .join(ScanRun, ScanRun.id == ScanJob.scan_run_id)
            .where(
                ScanJob.hotel_id.in_(hotel_ids),
                ScanRun.channel == channel,
                ScanRun.started_at >= since,
                ScanJob.status != "failed",
            )
        )
        return {r[0] for r in rows}

    async def latest_finished_run_ids(self, limit: int = 1) -> list[int]:
        rows = await self._s.execute(
            select(ScanRun.id)
            .where(ScanRun.status.in_(["completed", "partial"]))
            .order_by(ScanRun.finished_at.desc())
            .limit(limit)
        )
        return [r[0] for r in rows]
