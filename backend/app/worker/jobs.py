from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

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


class HotelPageNotFound(RuntimeError):
    pass


class JobFailed(RuntimeError):
    pass


class PermanentJobFailure(JobFailed):
    """Lỗi không tự hết khi thử lại (VD trang khách sạn 404): không chờ arq retry."""


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


@dataclass
class JobSummary:
    scan_run_id: int
    hotel_id: int
    probed: int = 0
    skipped: int = 0
    failed: int = 0
    run_finished: bool = False


async def run_probe_hotel(
    deps: WorkerDeps, scan_run_id: int, hotel_id: int, final_attempt: bool
) -> JobSummary:
    summary = JobSummary(scan_run_id, hotel_id)
    log_ctx = log.bind(run_id=scan_run_id, hotel_id=hotel_id, worker=deps.worker_id)

    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        job = await runs.start_job(scan_run_id, hotel_id, deps.clock.now())
        if job is None:
            log_ctx.info("job_already_done")
            return summary
        hotel = await runs.load_hotel(hotel_id)
        start_date, horizon = job.start_date, job.horizon_days
        await s.commit()

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
        if not calendar.ok:
            log_ctx.warning("calendar_unavailable", error=calendar.error)

        for offset in range(horizon):
            stay_date = start_date + timedelta(days=offset)
            if stay_date in done_dates:
                continue
            day = calendar.day(stay_date) if calendar.ok else None
            fetched_at = deps.clock.now()

            if day is not None and not day.available:
                async with deps.session_factory() as s:
                    await SnapshotRepository(s, deps.page_cap).write_skipped(
                        scan_run_id,
                        hotel_id,
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
                raise HotelPageNotFound(f"hotel page not found (http 404): {hotel.canonical_url}")
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
    log_ctx.info("job_done", probed=summary.probed, skipped=summary.skipped, failed=summary.failed)
    return summary
