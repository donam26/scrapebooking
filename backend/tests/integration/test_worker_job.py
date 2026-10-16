from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.booking.results import failed_result
from app.collector.fake import FakeCollector
from app.collector.storage import MemoryRawStore
from app.db.models import HotelCalendar, Listing, Probe, RoomSnapshot, ScanJob, ScanRun
from app.domain.models import CalendarDay, CalendarResult, ListingRef, ProbeMethod, ProbeStatus
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.repo.snapshots import SnapshotRepository
from app.worker.jobs import (
    JobFailed,
    PermanentJobFailure,
    TierPolicy,
    WorkerDeps,
    fail_job,
    run_probe_hotel,
)
from tests.fakes import OFFER
from tests.integration.seed import add_hotel

NOW = datetime(2026, 9, 23, 23, 5, tzinfo=UTC)
START = date(2026, 9, 24)


async def _seed(db: AsyncSession, horizon: int = 3, channel: str = "booking") -> tuple[int, int]:
    hotel = await add_hotel(db, "vn/h1")
    run = await ScanRunRepository(db).create_run(
        f"k:{channel}", NOW, [HotelJobPlan(hotel.id, START, horizon)], channel
    )
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
    # Đêm lịch báo đóng vẫn được probe trang để tách hết phòng / đóng ngày đến; trang không đọc được
    # (ở đây: chưa kịch bản → lỗi) thì giữ kết luận của lịch.
    assert collector.probe_calls == [
        (hotel_id, START, 1, 2),
        (hotel_id, START + timedelta(days=1), 1, 2),
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
    # Đêm lịch báo đóng (hạn chế) không phải hết phòng: không đếm vào sold_out_count.
    assert run.ok_count == 2 and run.sold_out_count == 0


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

    h1 = await add_hotel(db, "vn/h1")
    h2 = await add_hotel(db, "vn/h2")
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
    # Listing hỏng thì ngừng quét tới khi người dùng sửa.
    statuses = dict((await db.execute(select(Listing.channel, Listing.status))).tuples().all())
    assert statuses == {"booking": "broken"}


async def _old_probe(
    db: AsyncSession, hotel_id: int, stay: date, age: timedelta, status: ProbeStatus
) -> None:
    old = await ScanRunRepository(db).create_run(
        f"old:{stay}:{status}", NOW - age, [HotelJobPlan(hotel_id, START, 1)]
    )
    assert old is not None
    collector = FakeCollector()
    collector.set_probe(hotel_id, stay, status, offers=(OFFER,) if status == ProbeStatus.OK else ())
    result = await collector.probe(ListingRef(hotel_id, "booking", "vn/h1", "u", "vn"), stay, 1, 2)
    await SnapshotRepository(db, 10).write_probe(
        old.id, hotel_id, "booking", stay, result, None, "1", "vn", NOW - age
    )
    await db.commit()


async def test_tiering_skips_mid_and_far_nights_observed_recently(db: AsyncSession) -> None:
    # Gần (offset 0): luôn quét. Giữa (offset 1-2): bỏ nếu đã quan sát < 20h. Xa (offset 3): < 66h.
    run_id, hotel_id = await _seed(db, horizon=4)
    d = [START + timedelta(days=i) for i in range(4)]
    await _old_probe(db, hotel_id, d[0], timedelta(hours=1), ProbeStatus.OK)  # gần: vẫn quét
    await _old_probe(db, hotel_id, d[1], timedelta(hours=2), ProbeStatus.OK)  # giữa, mới: bỏ
    await _old_probe(db, hotel_id, d[2], timedelta(hours=2), ProbeStatus.BLOCKED)  # không dùng được
    await _old_probe(db, hotel_id, d[3], timedelta(hours=70), ProbeStatus.SOLD_OUT)  # xa, cũ: quét
    collector = FakeCollector()
    for day in d:
        collector.set_probe(hotel_id, day, ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    deps.tiers = TierPolicy(
        near_days=1, mid_days=3, mid_max_age=timedelta(hours=20), far_max_age=timedelta(hours=66)
    )
    summary = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert [c[1] for c in collector.probe_calls] == [d[0], d[2], d[3]]
    assert (summary.probed, summary.fresh, summary.run_finished) == (3, 1, True)
    run = await db.get(ScanRun, run_id)
    assert run is not None and run.status == "completed"


async def test_tiering_disabled_probes_every_night(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    await _old_probe(db, hotel_id, START + timedelta(days=1), timedelta(hours=1), ProbeStatus.OK)
    collector = FakeCollector()
    deps = _deps(db, collector, MemoryRawStore())
    deps.tiers = None
    summary = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert len(collector.probe_calls) == 2 and summary.fresh == 0


async def test_fail_job_closes_job_without_probing(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    finished: list[int] = []

    async def hook(run_id_: int) -> None:
        finished.append(run_id_)

    collector = FakeCollector()
    deps = _deps(db, collector, MemoryRawStore())
    deps.on_run_finished = hook
    assert await fail_job(deps, run_id, hotel_id, "channel paused (block rate)") is True
    assert collector.probe_calls == [] and finished == [run_id]
    db.expire_all()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert (job.status, job.error) == ("failed", "channel paused (block rate)")
    assert (await db.get(ScanRun, run_id)).status == "partial"  # type: ignore[union-attr]
    # Gọi lại (arq chạy lại job): không làm gì.
    assert await fail_job(deps, run_id, hotel_id, "again") is False


def _closed_middle_night(collector: FakeCollector, hotel_id: int) -> date:
    """Lịch 3 đêm, đêm giữa không nhận khách; đêm đầu và cuối còn phòng."""
    closed = START + timedelta(days=1)
    collector.set_calendar(
        hotel_id,
        _calendar((START, True, 1), (closed, False, 1), (START + timedelta(days=2), True, 1)),
    )
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(hotel_id, START + timedelta(days=2), ProbeStatus.OK, offers=(OFFER,))
    return closed


async def _statuses(db: AsyncSession) -> list[str]:
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    return [p.status for p in probes]


async def test_closed_night_with_rooms_on_the_page_is_available(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    closed = _closed_middle_night(collector, hotel_id)
    collector.set_probe(hotel_id, closed, ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert await _statuses(db) == ["ok", "ok", "ok"]


async def test_closed_night_sold_out_even_when_arriving_the_day_before_is_sold_out(
    db: AsyncSession,
) -> None:
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    closed = _closed_middle_night(collector, hotel_id)
    collector.set_probe(hotel_id, closed, ProbeStatus.SOLD_OUT)
    collector.set_stay_probe(hotel_id, START, 2, ProbeStatus.SOLD_OUT)
    summary = await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert await _statuses(db) == ["ok", "sold_out", "ok"]
    assert (hotel_id, START, 2, 2) in collector.probe_calls  # probe bắc cầu D-1 → D+1
    assert (summary.probed, summary.skipped) == (3, 0)


async def test_closed_night_bookable_from_the_day_before_is_only_closed_to_arrival(
    db: AsyncSession,
) -> None:
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    closed = _closed_middle_night(collector, hotel_id)
    collector.set_probe(hotel_id, closed, ProbeStatus.SOLD_OUT)
    collector.set_stay_probe(hotel_id, START, 2, ProbeStatus.OK, offers=(OFFER,))
    summary = await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert await _statuses(db) == ["ok", "skipped_calendar", "ok"]
    assert (summary.probed, summary.skipped) == (2, 1)
    # Probe bắc cầu (2 đêm từ hôm trước) không ghi thành dữ liệu của đêm nào.
    assert len((await db.execute(select(RoomSnapshot))).scalars().all()) == 2


async def test_closed_first_night_stays_restricted(db: AsyncSession) -> None:
    """Đêm đầu cửa sổ (tối nay) không bắc cầu được; trang "hết" có thể chỉ là chặn đặt trong ngày
    sau giờ cắt → giữ "hạn chế", chỉ kết luận hết phòng khi có bằng chứng."""
    run_id, hotel_id = await _seed(db, horizon=2)
    collector = FakeCollector()
    collector.set_calendar(
        hotel_id, _calendar((START, False, 1), (START + timedelta(days=1), True, 1))
    )
    collector.set_probe(hotel_id, START, ProbeStatus.SOLD_OUT)
    collector.set_probe(hotel_id, START + timedelta(days=1), ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert await _statuses(db) == ["skipped_calendar", "ok"]
    assert [c for c in collector.probe_calls if c[2] == 2] == []  # không có hôm trước để bắc cầu


async def test_closed_block_of_nights_stays_restricted(db: AsyncSession) -> None:
    """Hôm trước cũng đóng (một khối đêm đóng bán trên Booking trông y như hết phòng)."""
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    d1, d2 = START + timedelta(days=1), START + timedelta(days=2)
    collector.set_calendar(hotel_id, _calendar((START, True, 1), (d1, False, 1), (d2, False, 1)))
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(hotel_id, d1, ProbeStatus.SOLD_OUT)
    collector.set_probe(hotel_id, d2, ProbeStatus.SOLD_OUT)
    collector.set_stay_probe(hotel_id, START, 2, ProbeStatus.SOLD_OUT)
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    # Đêm 2: bắc cầu từ đêm 1 (còn bán) cũng hết → hết phòng; đêm 3: hôm trước cũng đóng → hạn chế.
    assert await _statuses(db) == ["ok", "sold_out", "skipped_calendar"]


async def test_bridge_is_skipped_when_the_day_before_needs_three_nights(db: AsyncSession) -> None:
    """minLOS hôm trước ≥3: probe bắc cầu phủ cả đêm sau, "hết" không chỉ ra đêm nào → hạn chế."""
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    closed = START + timedelta(days=1)
    collector.set_calendar(
        hotel_id,
        _calendar((START, True, 3), (closed, False, 1), (START + timedelta(days=2), True, 1)),
    )
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,), nights=3)
    collector.set_probe(hotel_id, closed, ProbeStatus.SOLD_OUT)
    collector.set_probe(hotel_id, START + timedelta(days=2), ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert await _statuses(db) == ["ok", "skipped_calendar", "ok"]
    # Chỉ có probe thường của đêm đầu (3 đêm), không có probe bắc cầu nào.
    assert collector.probe_calls.count((hotel_id, START, 3, 2)) == 1


async def test_capacity_ladder_measures_whole_hotel_rooms_left(db: AsyncSession) -> None:
    """Trang: mỗi đêm 1 loại phòng còn 2 (sàn 2). Thang nbRooms (5, 10): đêm 1 còn ≥5 nhưng không
    tới 10 → 5–9; đêm 2 không tới 5 → ≤4; đêm 3 còn ≥10."""
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    d1, d2, d3 = START, START + timedelta(days=1), START + timedelta(days=2)
    collector.set_calendar(hotel_id, _calendar((d1, True, 1), (d2, True, 1), (d3, True, 1)))
    collector.set_calendar(
        hotel_id, _calendar((d1, True, 1), (d2, False, 1), (d3, True, 1)), rooms=5
    )
    collector.set_calendar(hotel_id, _calendar((d1, False, 1), (d3, True, 1)), rooms=10)
    for d in (d1, d2, d3):
        collector.set_probe(hotel_id, d, ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    deps.capacity_rungs = (5, 10)
    await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)

    rows = (
        await db.execute(
            select(
                HotelCalendar.stay_date, HotelCalendar.rooms_min, HotelCalendar.rooms_max
            ).order_by(HotelCalendar.stay_date)
        )
    ).all()
    assert [tuple(r) for r in rows] == [(d1, 5, 9), (d2, None, 4), (d3, 10, None)]
    # Một request lịch cho mỗi nấc, mỗi request phủ cả cửa sổ đêm cần đo.
    assert [(c[1], c[3]) for c in collector.calendar_calls] == [(d1, 1), (d1, 5), (d1, 10)]


async def test_capacity_ladder_is_off_by_default(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=1)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, True)
    assert len(collector.calendar_calls) == 1


class _LadderBreaks(FakeCollector):
    """Lịch nấc 10 ném lỗi (VD hết ngân sách request): giữ kết quả các nấc trước."""

    async def fetch_calendar(  # type: ignore[override]
        self, hotel: ListingRef, start: date, days: int, adults: int, rooms: int = 1
    ) -> CalendarResult:
        if rooms == 10:
            raise RuntimeError("budget exhausted")
        return await super().fetch_calendar(hotel, start, days, adults, rooms)


async def test_capacity_ladder_keeps_measured_rungs_when_a_rung_raises(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=1)
    collector = _LadderBreaks()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    collector.set_calendar(hotel_id, _calendar((START, True, 1)), rooms=5)
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    deps.capacity_rungs = (5, 10)
    summary = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert summary.probed == 1
    row = (await db.execute(select(HotelCalendar.rooms_min, HotelCalendar.rooms_max))).one()
    assert tuple(row) == (5, None)


async def test_capacity_ladder_skips_nights_the_calendar_says_are_closed(db: AsyncSession) -> None:
    """Lịch (cũ) báo đóng nhưng trang còn phòng: ở mọi nấc lịch vẫn báo không → trần giả "≤4"."""
    run_id, hotel_id = await _seed(db, horizon=1)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, False, 1)))
    collector.set_calendar(hotel_id, _calendar((START, False, 1)), rooms=5)
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    deps.capacity_rungs = (5,)
    await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert await _statuses(db) == ["ok"]
    row = (await db.execute(select(HotelCalendar.rooms_min, HotelCalendar.rooms_max))).one()
    assert tuple(row) == (None, None)
    assert [c[3] for c in collector.calendar_calls] == [1]  # không gọi nấc nào
