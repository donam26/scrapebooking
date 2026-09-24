from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.db.models import Hotel, ScanJob, ScanRun, Tenant, TenantHotel
from app.ops.alerts import NullAlerter
from app.scheduler.service import SchedulerService


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[int, int]] = []

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None:
        self.enqueued.append((scan_run_id, hotel_id))


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
    h1 = Hotel(booking_url="u1", booking_slug="vn/h1", country_code="vn")
    h2 = Hotel(booking_url="u2", booking_slug="vn/h2", country_code="vn")
    db.add_all([t1, t2, h1, h2])
    await db.flush()
    db.add_all(
        [
            TenantHotel(tenant_id=t1.id, hotel_id=h1.id, role="self", active=True),
            TenantHotel(tenant_id=t2.id, hotel_id=h1.id, role="competitor", active=True),
            TenantHotel(tenant_id=t2.id, hotel_id=h2.id, role="competitor", active=True),
        ]
    )
    await db.commit()
    return t1.id, h1.id, h2.id


def _service(db: AsyncSession, queue: FakeQueue, clock: FixedClock) -> SchedulerService:
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return SchedulerService(
        session_factory=factory,
        queue=queue,
        clock=clock,
        deadline=timedelta(minutes=90),
        alerter=NullAlerter(),
        lookback=timedelta(minutes=10),
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
