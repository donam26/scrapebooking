from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.collector.base import Collector
from app.collector.booking.results import failed_result
from app.collector.storage import RawStore, raw_key
from app.domain.models import ProbeMethod, ProbeStatus
from app.logging import get_logger
from app.ops.alerts import Alerter, RunStats, run_summary_alert
from app.ops.metrics import JOBS_TOTAL, PROBE_DURATION, PROBES_TOTAL
from app.repo.runs import ScanRunRepository
from app.repo.snapshots import SnapshotRepository

log = get_logger(__name__)

# Gọi khi một scan run vừa chốt (giai đoạn 2: đẩy job analytics).
RunFinishedHook = Callable[[int], Awaitable[None]]
# Gọi trước mỗi job: đồng bộ sức khoẻ proxy từ lần kiểm tra của scheduler (roadmap 0.2).
BeforeJobHook = Callable[[], Awaitable[None]]


class HotelPageNotFound(RuntimeError):
    pass


class JobFailed(RuntimeError):
    pass


class PermanentJobFailure(JobFailed):
    """Lỗi không tự hết khi thử lại (VD trang khách sạn 404): không chờ arq retry."""


@dataclass(frozen=True)
class TierPolicy:
    """Quét theo tầng (D12). Đêm cách `start_date` dưới `near_days` ngày: quét mọi lượt. Dưới
    `mid_days`: bỏ qua nếu đã có quan sát dùng được trong `mid_max_age`. Xa hơn: `far_max_age`.
    Giữ số request gần như cũ khi nới horizon 30 → 90."""

    near_days: int = 14
    mid_days: int = 60
    mid_max_age: timedelta = timedelta(hours=20)
    far_max_age: timedelta = timedelta(hours=66)

    def max_age(self, offset_days: int) -> timedelta | None:
        if offset_days < self.near_days:
            return None
        return self.mid_max_age if offset_days < self.mid_days else self.far_max_age


@dataclass
class WorkerDeps:
    session_factory: async_sessionmaker[AsyncSession]
    collector: Collector
    raw_store: RawStore
    clock: Clock
    page_cap: int
    default_adults: int
    parser_version: str
    alerter: Alerter
    worker_id: str
    on_run_finished: RunFinishedHook | None = None
    tiers: TierPolicy | None = field(default_factory=TierPolicy)
    before_job: BeforeJobHook | None = None


@dataclass
class JobSummary:
    scan_run_id: int
    hotel_id: int
    probed: int = 0
    skipped: int = 0
    failed: int = 0
    fresh: int = 0  # đêm bỏ qua theo tầng (đã có quan sát đủ mới)
    run_finished: bool = False


async def _fresh_dates(
    deps: WorkerDeps, hotel_id: int, channel: str, start_date: date, horizon: int
) -> set[date]:
    """Đêm ở tầng giữa/xa đã có quan sát dùng được đủ mới: lượt này không cần quét lại."""
    if deps.tiers is None:
        return set()
    now = deps.clock.now()
    by_age: dict[date, timedelta] = {}
    for offset in range(horizon):
        max_age = deps.tiers.max_age(offset)
        if max_age is not None:
            by_age[start_date + timedelta(days=offset)] = max_age
    if not by_age:
        return set()
    async with deps.session_factory() as s:
        last = await SnapshotRepository(s, deps.page_cap).last_usable_probe_at(
            hotel_id, channel, list(by_age)
        )
    return {d for d, max_age in by_age.items() if d in last and now - last[d] < max_age}


async def run_probe_hotel(
    deps: WorkerDeps, scan_run_id: int, hotel_id: int, final_attempt: bool
) -> JobSummary:
    summary = JobSummary(scan_run_id, hotel_id)
    log_ctx = log.bind(run_id=scan_run_id, hotel_id=hotel_id, worker=deps.worker_id)
    if deps.before_job is not None:
        try:
            await deps.before_job()
        except Exception:  # noqa: BLE001 — đồng bộ sức khoẻ proxy lỗi không được chặn job
            log_ctx.exception("before_job_hook_failed")

    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        job = await runs.start_job(scan_run_id, hotel_id, deps.clock.now())
        if job is None:
            log_ctx.info("job_already_done")
            return summary
        channel = await runs.run_channel(scan_run_id)
        listing = await runs.load_listing(hotel_id, channel)
        start_date, horizon = job.start_date, job.horizon_days
        if listing is None:
            now = deps.clock.now()
            await runs.finish_job(scan_run_id, hotel_id, "failed", now, "listing_inactive")
            summary.run_finished = await runs.try_finish_run(scan_run_id, now)
        await s.commit()
    if listing is None:
        log_ctx.info("job_listing_inactive", channel=channel)
        if summary.run_finished and deps.on_run_finished is not None:
            await deps.on_run_finished(scan_run_id)
        return summary
    hotel = listing

    status, error = "done", None
    permanent = False
    try:
        calendar = await deps.collector.fetch_calendar(
            hotel, start_date, horizon, deps.default_adults
        )
        async with deps.session_factory() as s:
            snaps = SnapshotRepository(s, deps.page_cap)
            await snaps.write_calendar(hotel_id, scan_run_id, calendar, deps.clock.now())
            done_dates = await snaps.terminal_dates(scan_run_id, hotel_id)
            await s.commit()
        if not calendar.ok and calendar.error != "unsupported":
            log_ctx.warning("calendar_unavailable", error=calendar.error)
        fresh_dates = await _fresh_dates(deps, hotel_id, channel, start_date, horizon)
        summary.fresh = len(fresh_dates)

        for offset in range(horizon):
            stay_date = start_date + timedelta(days=offset)
            if stay_date in done_dates or stay_date in fresh_dates:
                continue
            day = calendar.day(stay_date) if calendar.ok else None
            fetched_at = deps.clock.now()

            if day is not None and not day.available:
                async with deps.session_factory() as s:
                    await SnapshotRepository(s, deps.page_cap).write_skipped(
                        scan_run_id,
                        hotel_id,
                        channel,
                        stay_date,
                        nights=day.min_length_of_stay,
                        adults=deps.default_adults,
                        fetched_at=fetched_at,
                    )
                    await s.commit()
                PROBES_TOTAL.labels(
                    str(ProbeStatus.SKIPPED_CALENDAR), str(ProbeMethod.CALENDAR)
                ).inc()
                summary.skipped += 1
                continue

            nights = day.min_length_of_stay if day is not None else 1
            try:
                result = await deps.collector.probe(hotel, stay_date, nights, deps.default_adults)
            except Exception as exc:  # noqa: BLE001
                log_ctx.exception("probe_raised", stay_date=str(stay_date))
                result = failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.HTTP,
                    checkin=stay_date,
                    nights=nights,
                    adults=deps.default_adults,
                    error=f"{type(exc).__name__}: {exc}",
                )

            key: str | None = None
            if result.raw_html:
                key = raw_key(scan_run_id, hotel_id, stay_date, fetched_at)
                try:
                    await deps.raw_store.put_html(key, result.raw_html)
                except Exception:  # noqa: BLE001
                    log_ctx.exception("raw_store_failed", key=key)
                    key = None

            async with deps.session_factory() as s:
                await SnapshotRepository(s, deps.page_cap).write_probe(
                    scan_run_id,
                    hotel_id,
                    channel,
                    stay_date,
                    result,
                    key,
                    deps.parser_version,
                    hotel.country_code,
                    fetched_at,
                )
                await s.commit()

            PROBES_TOTAL.labels(str(result.status), str(result.method)).inc()
            PROBE_DURATION.observe(result.duration_ms / 1000)
            summary.probed += 1
            if result.status in (ProbeStatus.BLOCKED, ProbeStatus.ERROR):
                summary.failed += 1
            if result.status == ProbeStatus.ERROR and result.error == "not_found":
                # Trang khách sạn 404 (URL/slug sai): mọi ngày khác cũng 404, dừng thay vì quét hết.
                raise HotelPageNotFound(f"hotel page not found (http 404): {hotel.url}")
    except Exception as exc:  # noqa: BLE001
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        permanent = isinstance(exc, HotelPageNotFound)
        log_ctx.exception("job_failed")

    now = deps.clock.now()
    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        # Lỗi chưa phải lần cuối: arq sẽ chạy lại, job vẫn chờ nên run chưa được chốt.
        job_status = (
            "retrying" if status == "failed" and not (final_attempt or permanent) else status
        )
        await runs.finish_job(scan_run_id, hotel_id, job_status, now, error)
        if permanent:
            # URL listing hỏng (404): ngừng quét listing này tới khi người dùng sửa URL.
            await SnapshotRepository(s, deps.page_cap).mark_listing_broken(
                hotel_id, channel, error or "not found"
            )
        if job_status != "retrying":
            summary.run_finished = await runs.try_finish_run(scan_run_id, now)
        await s.commit()
        if summary.run_finished:
            run = await runs.get_run(scan_run_id)
            msg = run_summary_alert(
                RunStats(
                    run.id,
                    run.total_probes,
                    run.ok_count,
                    run.sold_out_count,
                    run.blocked_count,
                    run.error_count,
                )
            )
            log_ctx.info(
                "scan_run_finished", status=run.status, ok=run.ok_count, blocked=run.blocked_count
            )
            if msg:
                await deps.alerter.send(msg)

    if summary.run_finished and deps.on_run_finished is not None:
        try:
            await deps.on_run_finished(scan_run_id)
        except Exception:  # noqa: BLE001
            log_ctx.exception("run_finished_hook_failed")

    JOBS_TOTAL.labels(status).inc()
    if status == "failed":
        raise (PermanentJobFailure if permanent else JobFailed)(error or "unknown")
    log_ctx.info(
        "job_done",
        channel=channel,
        probed=summary.probed,
        skipped=summary.skipped,
        fresh=summary.fresh,
        failed=summary.failed,
    )
    return summary


async def fail_job(deps: WorkerDeps, scan_run_id: int, hotel_id: int, error: str) -> bool:
    """Chốt job thất bại mà không quét (kênh đang tạm dừng). Trả True nếu nhờ đó run được chốt."""
    now = deps.clock.now()
    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        job = await runs.start_job(scan_run_id, hotel_id, now)
        if job is None:
            return False
        await runs.finish_job(scan_run_id, hotel_id, "failed", now, error)
        finished = await runs.try_finish_run(scan_run_id, now)
        await s.commit()
    if finished and deps.on_run_finished is not None:
        await deps.on_run_finished(scan_run_id)
    return finished
