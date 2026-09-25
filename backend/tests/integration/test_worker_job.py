from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.booking.results import failed_result
from app.collector.fake import FakeCollector
from app.collector.storage import MemoryRawStore
from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, ScanJob, ScanRun
from app.domain.models import CalendarDay, CalendarResult, ProbeMethod, ProbeStatus
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.worker.jobs import JobFailed, PermanentJobFailure, WorkerDeps, run_probe_hotel
from tests.fakes import OFFER

NOW = datetime(2026, 9, 23, 23, 5, tzinfo=UTC)
START = date(2026, 9, 24)


async def _seed(db: AsyncSession, horizon: int = 3) -> tuple[int, int]:
    hotel = Hotel(booking_url="u", booking_slug="vn/h1", country_code="vn")
    db.add(hotel)
    await db.flush()
    run = await ScanRunRepository(db).create_run("k", NOW, [HotelJobPlan(hotel.id, START, horizon)])
    assert run is not None
    await db.commit()
    return run.id, hotel.id


def _deps(db: AsyncSession, collector: FakeCollector, store: MemoryRawStore) -> WorkerDeps:
    return WorkerDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector,
        raw_store=store,
        clock=FixedClock(NOW),
        page_cap=10,
        default_adults=2,
        parser_version="1",
        alerter=NullAlerter(),
        worker_id="w1",
    )


def _calendar(*days: tuple[date, bool, int]) -> CalendarResult:
    return CalendarResult(ok=True, days=tuple(CalendarDay(d, a, m, None) for d, a, m in days))


async def test_happy_path_probes_skips_and_finishes_run(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    collector.set_calendar(
        hotel_id,
        _calendar(
            (START, True, 1),
            (START + timedelta(days=1), False, 1),
            (START + timedelta(days=2), True, 2),
        ),
    )
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(
        hotel_id, START + timedelta(days=2), ProbeStatus.OK, offers=(OFFER,), nights=2
    )
    store = MemoryRawStore()
    finished: list[int] = []

    async def hook(run_id_: int) -> None:
        finished.append(run_id_)

    deps = _deps(db, collector, store)
    deps.on_run_finished = hook
    summary = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)

    assert (summary.probed, summary.skipped, summary.failed, summary.run_finished) == (
        2,
        1,
        0,
        True,
    )
    assert finished == [run_id]
    assert collector.probe_calls == [
        (hotel_id, START, 1, 2),
        (hotel_id, START + timedelta(days=2), 2, 2),
    ]
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["ok", "skipped_calendar", "ok"]
    assert probes[2].nights == 2
    assert probes[0].raw_object_key in store.items
    assert len((await db.execute(select(RoomSnapshot))).scalars().all()) == 2
    assert len((await db.execute(select(HotelCalendar))).scalars().all()) == 3
    job = (await db.execute(select(ScanJob))).scalar_one()
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert job.status == "done" and run.status == "completed"
    assert run.ok_count == 2 and run.sold_out_count == 1


async def test_rerun_is_idempotent(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    collector = FakeCollector()
    collector.set_calendar(
        hotel_id, _calendar((START, True, 1), (START + timedelta(days=1), True, 1))
    )
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(hotel_id, START + timedelta(days=1), ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    second = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert second.probed == 0 and len(collector.probe_calls) == 2
    assert len((await db.execute(select(Probe))).scalars().all()) == 2


async def test_calendar_failure_probes_every_day_with_one_night(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    collector = FakeCollector()  # calendar không kịch bản -> ok=False
    collector.set_probe(hotel_id, START, ProbeStatus.NO_ROOMS_1N)
    collector.set_probe(hotel_id, START + timedelta(days=1), ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(
        _deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True
    )
    assert [c[2] for c in collector.probe_calls] == [1, 1]
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["no_rooms_1n", "ok"]


async def test_blocked_probe_is_recorded_and_retried_next_run_only(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=1)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    collector.set_probe(hotel_id, START, ProbeStatus.BLOCKED, raw_html=None)
    summary = await run_probe_hotel(
        _deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True
    )
    assert summary.failed == 1 and summary.run_finished
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.status == "completed" and run.blocked_count == 1


async def test_collector_exception_becomes_error_probe(db: AsyncSession) -> None:
    class Exploding(FakeCollector):
        async def probe(self, hotel, checkin, nights, adults):  # type: ignore[no-untyped-def]
            raise RuntimeError("kaboom")

    run_id, hotel_id = await _seed(db, horizon=1)
    collector = Exploding()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    summary = await run_probe_hotel(
        _deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True
    )
    assert summary.failed == 1
    probe = (await db.execute(select(Probe))).scalar_one()
    assert probe.status == "error" and "kaboom" in (probe.error or "")


async def test_fatal_error_marks_job_failed_and_raises(db: AsyncSession) -> None:
    class BrokenCalendar(FakeCollector):
        async def fetch_calendar(self, hotel, start, days, adults):  # type: ignore[no-untyped-def]
            raise RuntimeError("db gone")

    run_id, hotel_id = await _seed(db, horizon=1)
    deps = _deps(db, BrokenCalendar(), MemoryRawStore())
    try:
        await run_probe_hotel(deps, run_id, hotel_id, final_attempt=False)
    except JobFailed as exc:
        assert "db gone" in str(exc)
    else:
        raise AssertionError("expected JobFailed")
    job = (await db.execute(select(ScanJob))).scalar_one()
    run = (await db.execute(select(ScanRun))).scalar_one()
    # chưa phải lần cuối: job chờ retry (không phải trạng thái cuối), run vẫn chạy
    assert job.status == "retrying" and "db gone" in (job.error or "")
    assert run.status == "running"

    try:
        await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    except JobFailed:
        pass
    db.expire_all()
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.status == "partial"


async def test_other_job_finishing_does_not_close_run_while_one_waits_for_retry(
    db: AsyncSession,
) -> None:
    class BrokenFor(FakeCollector):
        def __init__(self, broken_id: int) -> None:
            super().__init__()
            self.broken_id = broken_id

        async def fetch_calendar(self, hotel, start, days, adults):  # type: ignore[no-untyped-def]
            if hotel.id == self.broken_id:
                raise RuntimeError("calendar timeout")
            return await super().fetch_calendar(hotel, start, days, adults)

    h1 = Hotel(booking_url="u1", booking_slug="vn/h1", country_code="vn")
    h2 = Hotel(booking_url="u2", booking_slug="vn/h2", country_code="vn")
    db.add_all([h1, h2])
    await db.flush()
    run = await ScanRunRepository(db).create_run(
        "k2", NOW, [HotelJobPlan(h1.id, START, 1), HotelJobPlan(h2.id, START, 1)]
    )
    assert run is not None
    await db.commit()
    run_id, broken, healthy = run.id, h1.id, h2.id
    collector = BrokenFor(broken)
    collector.set_calendar(healthy, _calendar((START, True, 1)))
    collector.set_probe(healthy, START, ProbeStatus.OK, offers=(OFFER,))
    finished: list[int] = []

    async def hook(run_id_: int) -> None:
        finished.append(run_id_)

    deps = _deps(db, collector, MemoryRawStore())
    deps.on_run_finished = hook

    try:
        await run_probe_hotel(deps, run_id, broken, final_attempt=False)
    except JobFailed:
        pass
    await run_probe_hotel(deps, run_id, healthy, final_attempt=False)
    db.expire_all()
    assert (await db.get(ScanRun, run_id)).status == "running"  # type: ignore[union-attr]
    assert finished == []

    try:
        await run_probe_hotel(deps, run_id, broken, final_attempt=True)
    except JobFailed:
        pass
    db.expire_all()
    assert (await db.get(ScanRun, run_id)).status == "partial"  # type: ignore[union-attr]
    assert finished == [run_id]


async def test_hotel_page_not_found_stops_job_early(db: AsyncSession) -> None:
    # URL/slug sai (Booking 404): không probe tiếp từng ngày trong horizon, báo lỗi rõ ràng.
    class NotFound(FakeCollector):
        async def probe(self, hotel, checkin, nights, adults):  # type: ignore[no-untyped-def]
            self.probe_calls.append((hotel.id, checkin, nights, adults))
            return failed_result(
                ProbeStatus.ERROR,
                method=ProbeMethod.HTTP,
                checkin=checkin,
                nights=nights,
                adults=adults,
                error="not_found",
                http_status=404,
            )

    run_id, hotel_id = await _seed(db, horizon=5)
    collector = NotFound()
    try:
        # Lỗi vĩnh viễn: dù chưa phải lần cuối cũng không chờ arq thử lại.
        await run_probe_hotel(
            _deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=False
        )
    except PermanentJobFailure as exc:
        assert "404" in str(exc)
    else:
        raise AssertionError("expected PermanentJobFailure")
    assert len(collector.probe_calls) == 1
    db.expire_all()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert job.status == "failed" and "404" in (job.error or "")
