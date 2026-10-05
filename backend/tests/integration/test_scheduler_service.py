from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.db.models import Probe, ScanJob, ScanRun, Tenant, TenantHotel
from app.ops.alerts import NullAlerter
from app.scheduler.channel_pause import MemoryChannelPauses
from app.scheduler.service import SchedulerService
from tests.integration.seed import add_hotel, add_listing, scan_run


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[int, int]] = []
        self.channels: list[str] = []

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int, channel: str) -> None:
        self.enqueued.append((scan_run_id, hotel_id))
        self.channels.append(channel)


class RecordingAlerter:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def _seed(db: AsyncSession) -> tuple[int, int, int]:
    t1 = Tenant(
        name="A",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    t2 = Tenant(
        name="B",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00", "14:00"],
        horizon_days=45,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add_all([t1, t2])
    h1 = await add_hotel(db, "vn/h1")
    h2 = await add_hotel(db, "vn/h2")
    db.add_all(
        [
            TenantHotel(tenant_id=t1.id, hotel_id=h1.id, role="self", active=True),
            TenantHotel(tenant_id=t2.id, hotel_id=h1.id, role="competitor", active=True),
            TenantHotel(tenant_id=t2.id, hotel_id=h2.id, role="competitor", active=True),
        ]
    )
    await db.commit()
    return t1.id, h1.id, h2.id


def _service(
    db: AsyncSession,
    queue: FakeQueue,
    clock: FixedClock,
    pauses: MemoryChannelPauses | None = None,
    alerter: RecordingAlerter | None = None,
) -> SchedulerService:
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return SchedulerService(
        session_factory=factory,
        queue=queue,
        clock=clock,
        deadline=timedelta(minutes=90),
        alerter=alerter or NullAlerter(),
        lookback=timedelta(minutes=10),
        pauses=pauses,
    )


async def test_tick_creates_one_run_and_enqueues_unique_hotels(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))  # 06:02 VN
    report = await _service(db, queue, clock).tick()
    assert len(report.created_runs) == 1
    run_id = report.created_runs[0]
    assert sorted(queue.enqueued) == [(run_id, h1), (run_id, h2)]
    jobs = (await db.execute(select(ScanJob).order_by(ScanJob.hotel_id))).scalars().all()
    assert [(j.hotel_id, j.horizon_days) for j in jobs] == [(h1, 45), (h2, 45)]


async def test_tick_twice_does_not_duplicate(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    await svc.tick()
    clock.advance(minutes=1)
    report = await svc.tick()
    assert report.created_runs == []
    assert len((await db.execute(select(ScanRun))).scalars().all()) == 1


async def test_tick_expires_old_runs(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    first = await svc.tick()
    clock.advance(minutes=95)
    report = await svc.tick()
    assert report.expired_runs == first.created_runs


async def test_tick_reenqueues_stale_queued_jobs(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    await svc.tick()
    n = len(queue.enqueued)
    clock.advance(minutes=6)
    await svc.tick()
    assert len(queue.enqueued) == 2 * n


# ---- quét bù sau một quãng scheduler không chạy ----

DOWNTIME_END = datetime(2026, 9, 24, 3, 30, tzinfo=UTC)  # 10:30 VN, mốc 06:00 đã bị lỡ


async def _jobs(db: AsyncSession, run_id: int) -> list[tuple[int, str, int]]:
    rows = await db.execute(
        select(ScanJob).where(ScanJob.scan_run_id == run_id).order_by(ScanJob.hotel_id)
    )
    return [(j.hotel_id, j.start_date.isoformat(), j.horizon_days) for j in rows.scalars()]


async def test_first_tick_after_downtime_catches_up_missed_slot_once(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(DOWNTIME_END)
    svc = _service(db, queue, clock)
    report = await svc.tick()
    assert report.catch_up_run is not None and report.created_runs == [report.catch_up_run]
    run = await db.get(ScanRun, report.catch_up_run)
    assert run is not None and run.trigger_key == "catchup:2026-09-24T03:30:booking"
    assert run.started_at == DOWNTIME_END  # hạn chót tính từ lúc quét bù, không từ mốc đã lỡ
    # phạm vi quét tính từ hôm nay, horizon lớn nhất giữa các tenant
    assert await _jobs(db, run.id) == [(h1, "2026-09-24", 45), (h2, "2026-09-24", 45)]
    assert sorted(queue.enqueued) == [(run.id, h1), (run.id, h2)]

    clock.advance(minutes=1)
    assert (await svc.tick()).created_runs == []
    # Khởi động lại lần nữa: mốc đã được bù, không quét lại.
    assert (await _service(db, queue, clock).tick()).created_runs == []


async def test_restart_after_scheduled_run_does_not_catch_up(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))  # 06:02 VN
    [run_id] = (await _service(db, queue, clock).tick()).created_runs
    # worker quét xong run theo lịch
    await db.execute(update(ScanJob).where(ScanJob.scan_run_id == run_id).values(status="done"))
    await db.execute(update(ScanRun).where(ScanRun.id == run_id).values(status="completed"))
    await db.commit()
    clock.advance(hours=4)
    report = await _service(db, queue, clock).tick()  # scheduler mới khởi động
    assert report.catch_up_run is None and report.created_runs == []


async def test_catch_up_skips_hotels_scanned_since_missed_slot(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    # "Quét ngay" lúc 08:00 VN: h1 quét xong, h2 thất bại (proxy lỗi) -> chỉ h2 cần quét bù.
    db.add(scan_run("manual:t1:x:booking", datetime(2026, 9, 24, 1, 0, tzinfo=UTC)))
    await db.flush()
    manual = (await db.execute(select(ScanRun.id))).scalar_one()
    day = DOWNTIME_END.date()
    db.add_all(
        [
            ScanJob(
                scan_run_id=manual, hotel_id=h1, start_date=day, horizon_days=30, status="done"
            ),
            ScanJob(
                scan_run_id=manual,
                hotel_id=h2,
                start_date=day,
                horizon_days=30,
                status="failed",
                error="proxy 407",
            ),
        ]
    )
    await db.commit()
    report = await _service(db, FakeQueue(), FixedClock(DOWNTIME_END)).tick()
    assert report.catch_up_run is not None
    assert [h for h, _, _ in await _jobs(db, report.catch_up_run)] == [h2]


async def test_catch_up_after_tick_gap_while_running(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))  # 06:02 VN: run theo lịch
    svc = _service(db, queue, clock)
    await svc.tick()
    # Tick lỗi liên tục (mất DB…) từ trước 14:00 tới 14:30 VN: tenant B lỡ mốc 14:00.
    clock.advance(hours=8, minutes=28)
    report = await svc.tick()
    assert report.catch_up_run is not None
    assert [h for h, _, _ in await _jobs(db, report.catch_up_run)] == [h1, h2]


async def test_catch_up_covers_hotels_of_run_that_died_past_deadline(db: AsyncSession) -> None:
    # Run 06:00 được tạo rồi máy tắt: job còn "queued". Khởi động lại lúc 08:00 (quá hạn chót
    # 90 phút): run cũ bị chốt và khách sạn của nó phải được quét bù, không bị coi là "đã quét".
    _, h1, h2 = await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))  # 06:02 VN
    first = await _service(db, queue, clock).tick()
    clock.advance(hours=2)
    report = await _service(db, queue, clock).tick()
    assert report.expired_runs == first.created_runs
    assert report.reenqueued == 0  # job của run đã chết không bị đẩy lại
    assert report.catch_up_run is not None
    assert [h for h, _, _ in await _jobs(db, report.catch_up_run)] == [h1, h2]


# ---- đa kênh: một run mỗi (mốc × kênh), tự ngắt kênh bị chặn ----

SLOT = datetime(2026, 9, 23, 23, 2, tzinfo=UTC)  # 06:02 VN


async def test_one_run_per_channel_for_the_same_slot(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    await add_listing(db, h1, "agoda", "agoda-h1")
    await add_listing(db, h2, "agoda", "agoda-h2", status="unverified")  # chưa xác minh: chưa quét
    await add_listing(db, h2, "ivivu", "ivivu-h2", status="broken")
    await db.commit()
    queue = FakeQueue()
    report = await _service(db, queue, FixedClock(SLOT)).tick()
    runs = (
        (await db.execute(select(ScanRun).where(ScanRun.id.in_(report.created_runs))))
        .scalars()
        .all()
    )
    assert {(r.channel, r.trigger_key) for r in runs} == {
        ("agoda", "2026-09-23T23:00:agoda"),
        ("booking", "2026-09-23T23:00:booking"),
    }
    by_channel = {r.channel: r.id for r in runs}
    assert sorted(zip(queue.enqueued, queue.channels, strict=True)) == sorted(
        [
            ((by_channel["agoda"], h1), "agoda"),
            ((by_channel["booking"], h1), "booking"),
            ((by_channel["booking"], h2), "booking"),
        ]
    )


async def test_paused_listing_and_paused_tenant_hotel_are_not_scanned(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    await db.execute(update(TenantHotel).where(TenantHotel.hotel_id == h2).values(active=False))
    await add_listing(db, h1, "agoda", "agoda-h1", status="paused")
    await db.commit()
    queue = FakeQueue()
    report = await _service(db, queue, FixedClock(SLOT)).tick()
    assert len(report.created_runs) == 1
    assert queue.enqueued == [(report.created_runs[0], h1)] and queue.channels == ["booking"]


async def test_paused_channel_gets_no_run_other_channels_continue(db: AsyncSession) -> None:
    _, h1, _ = await _seed(db)
    await add_listing(db, h1, "agoda", "agoda-h1")
    await db.commit()
    clock = FixedClock(SLOT)
    pauses = MemoryChannelPauses(clock.now)
    await pauses.pause("agoda", 30, "test")
    queue = FakeQueue()
    report = await _service(db, queue, clock, pauses).tick()
    channels = (
        await db.execute(select(ScanRun.channel).where(ScanRun.id.in_(report.created_runs)))
    ).scalars()
    assert list(channels) == ["booking"]
    assert set(queue.channels) == {"booking"}


async def _probes(
    db: AsyncSession, run_id: int, hotel_id: int, channel: str, ok: int, blocked: int, at: datetime
) -> None:
    for i in range(ok + blocked):
        stay = date(2026, 10, 1) + timedelta(days=i)
        db.add(
            Probe(
                scan_run_id=run_id,
                hotel_id=hotel_id,
                channel=channel,
                stay_date=stay,
                checkin=stay,
                checkout=stay + timedelta(days=1),
                nights=1,
                adults=2,
                status="blocked" if i < blocked else "ok",
                fetched_at=at,
            )
        )
    await db.commit()


async def test_high_block_rate_pauses_only_that_channel_and_alerts(db: AsyncSession) -> None:
    _, h1, _ = await _seed(db)
    at = SLOT + timedelta(hours=3)  # ngoài mốc quét: tick chỉ kiểm tra tỉ lệ chặn
    agoda_run = scan_run("r-agoda", at - timedelta(minutes=20), channel="agoda", status="running")
    booking_run = scan_run("r-booking", at - timedelta(minutes=20), status="running")
    db.add_all([agoda_run, booking_run])
    await db.flush()
    await _probes(db, agoda_run.id, h1, "agoda", ok=10, blocked=15, at=at - timedelta(minutes=5))
    await _probes(db, booking_run.id, h1, "booking", ok=24, blocked=1, at=at - timedelta(minutes=5))
    clock = FixedClock(at)
    pauses = MemoryChannelPauses(clock.now)
    alerter = RecordingAlerter()
    svc = _service(db, FakeQueue(), clock, pauses, alerter)
    report = await svc.tick()
    assert report.paused_channels == ["agoda"]
    assert await pauses.is_paused("agoda") and not await pauses.is_paused("booking")
    assert any(a.startswith("[agoda]") and "60%" in a for a in alerter.sent)
    assert any("Channel agoda paused 30 min" in a for a in alerter.sent)
    assert not any(a.startswith("[booking]") or "Channel booking" in a for a in alerter.sent)

    # Đang tạm dừng: tick sau không dừng lại lần nữa; hết hạn thì kênh chạy lại.
    clock.advance(minutes=1)
    assert (await svc.tick()).paused_channels == []
    clock.advance(minutes=30)
    assert not await pauses.is_paused("agoda")
