from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Probe, ScanJob, ScanRun
from app.domain.models import HotelRef, ProbeStatus


@dataclass(frozen=True)
class HotelJobPlan:
    hotel_id: int
    start_date: date
    horizon_days: int


class ScanRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_run(
        self, trigger_key: str, scheduled_at: datetime, plans: list[HotelJobPlan]
    ) -> ScanRun | None:
        """Tạo run và job. Trả None nếu trigger_key đã tồn tại (đã tạo trước đó)."""
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

    async def load_hotel(self, hotel_id: int) -> HotelRef:
        hotel = (await self._s.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
        return HotelRef(
            id=hotel.id,
            country_code=hotel.country_code,
            slug=hotel.booking_slug,
            canonical_url=f"https://www.booking.com/hotel/{hotel.booking_slug}.html",
        )

    async def start_job(self, scan_run_id: int, hotel_id: int, now: datetime) -> ScanJob | None:
        """Chuyển job sang running. Trả None nếu job đã done (chạy lại không làm gì)."""
        job = (
            await self._s.execute(
                select(ScanJob).where(
                    ScanJob.scan_run_id == scan_run_id, ScanJob.hotel_id == hotel_id
                )
            )
        ).scalar_one_or_none()
        if job is None or job.status == "done":
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
        pending = await self._s.execute(
            select(func.count())
            .select_from(ScanJob)
            .where(ScanJob.scan_run_id == scan_run_id, ScanJob.status.in_(["queued", "running"]))
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
        await self._s.execute(
            update(ScanRun)
            .where(ScanRun.id == scan_run_id)
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
        return True

    async def expire_runs(self, deadline: timedelta, now: datetime) -> list[int]:
        cutoff = now - deadline
        rows = await self._s.execute(
            select(ScanRun.id).where(ScanRun.status == "running", ScanRun.started_at < cutoff)
        )
        expired = [r[0] for r in rows]
        for run_id in expired:
            await self._s.execute(
                update(ScanJob)
                .where(ScanJob.scan_run_id == run_id, ScanJob.status.in_(["queued", "running"]))
                .values(status="failed", finished_at=now, error="deadline")
            )
            await self.try_finish_run(run_id, now)
        return expired

    async def get_run(self, scan_run_id: int) -> ScanRun:
        return (
            await self._s.execute(select(ScanRun).where(ScanRun.id == scan_run_id))
        ).scalar_one()

    async def probe_stats_since(self, since: datetime) -> tuple[int, int]:
        """(tổng probe có request thật, số bị chặn) kể từ `since`."""
        rows = await self._s.execute(
            select(Probe.status, func.count())
            .where(Probe.fetched_at >= since, Probe.status != str(ProbeStatus.SKIPPED_CALENDAR))
            .group_by(Probe.status)
        )
        by_status = {row[0]: row[1] for row in rows}
        return sum(by_status.values()), by_status.get(str(ProbeStatus.BLOCKED), 0)

    async def stale_queued_jobs(self, queued_before: datetime) -> list[tuple[int, int]]:
        """Job vẫn 'queued' trong run đang chạy được tạo trước `queued_before`:
        cần đẩy lại hàng đợi."""
        rows = await self._s.execute(
            select(ScanJob.scan_run_id, ScanJob.hotel_id)
            .join(ScanRun, ScanRun.id == ScanJob.scan_run_id)
            .where(
                ScanJob.status == "queued",
                ScanRun.status == "running",
                ScanRun.started_at < queued_before,
            )
        )
        return [(r[0], r[1]) for r in rows]

    async def latest_finished_run_ids(self, limit: int = 1) -> list[int]:
        rows = await self._s.execute(
            select(ScanRun.id)
            .where(ScanRun.status.in_(["completed", "partial"]))
            .order_by(ScanRun.finished_at.desc())
            .limit(limit)
        )
        return [r[0] for r in rows]
