import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Hotel, Probe, ScanJob, ScanRun
from app.repo.runs import HotelJobPlan, ScanRunRepository

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)


async def _hotels(db: AsyncSession, n: int) -> list[int]:
    hotels = [
        Hotel(
            booking_url=f"https://www.booking.com/hotel/vn/h{i}.html",
            booking_slug=f"vn/h{i}",
            country_code="vn",
        )
        for i in range(n)
    ]
    db.add_all(hotels)
    await db.flush()
    return [h.id for h in hotels]


async def test_create_run_with_jobs_and_idempotent_key(db: AsyncSession) -> None:
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    plans = [
        HotelJobPlan(ids[0], date(2026, 9, 24), 30),
        HotelJobPlan(ids[1], date(2026, 9, 24), 45),
    ]
    run = await repo.create_run("2026-09-24T06:00", NOW, plans)
    await db.commit()
    assert run is not None and run.total_jobs == 2
    jobs = (await db.execute(select(ScanJob).order_by(ScanJob.hotel_id))).scalars().all()
    assert [(j.hotel_id, j.horizon_days, j.status) for j in jobs] == [
        (ids[0], 30, "queued"),
        (ids[1], 45, "queued"),
    ]
    assert await repo.create_run("2026-09-24T06:00", NOW, plans) is None


async def test_load_hotel_ref(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    ref = await ScanRunRepository(db).load_hotel(ids[0])
    assert ref.slug == "vn/h0" and ref.country_code == "vn" and ref.pagename == "h0"


async def test_job_lifecycle_and_run_completion(db: AsyncSession) -> None:
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(i, date(2026, 9, 24), 30) for i in ids])
    assert run is not None
    await db.commit()

    job = await repo.start_job(run.id, ids[0], NOW)
    assert job is not None and job.status == "running" and job.start_date == date(2026, 9, 24)
    assert await repo.try_finish_run(run.id, NOW) is False

    await repo.finish_job(run.id, ids[0], "done", NOW + timedelta(minutes=5))
    await repo.start_job(run.id, ids[1], NOW)
    await repo.finish_job(run.id, ids[1], "failed", NOW + timedelta(minutes=6), error="boom")
    db.add_all(
        [
            Probe(
                scan_run_id=run.id,
                hotel_id=ids[0],
                stay_date=date(2026, 10, 1),
                checkin=date(2026, 10, 1),
                checkout=date(2026, 10, 2),
                nights=1,
                adults=2,
                status="ok",
                fetched_at=NOW,
            ),
            Probe(
                scan_run_id=run.id,
                hotel_id=ids[0],
                stay_date=date(2026, 10, 2),
                checkin=date(2026, 10, 2),
                checkout=date(2026, 10, 3),
                nights=1,
                adults=2,
                status="blocked",
                fetched_at=NOW,
            ),
        ]
    )
    await db.flush()
    run_id = run.id
    assert await repo.try_finish_run(run_id, NOW + timedelta(minutes=7)) is True
    await db.commit()
    db.expire_all()

    run_row = (await db.execute(select(ScanRun).where(ScanRun.id == run_id))).scalar_one()
    assert run_row.status == "partial"
    assert run_row.total_probes == 2 and run_row.ok_count == 1 and run_row.blocked_count == 1
    assert run_row.finished_at == NOW + timedelta(minutes=7)
    assert await repo.latest_finished_run_ids() == [run_id]


async def test_start_job_is_idempotent_for_done_job(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await repo.start_job(run.id, ids[0], NOW)
    await repo.finish_job(run.id, ids[0], "done", NOW)
    assert await repo.start_job(run.id, ids[0], NOW) is None


async def test_expire_runs_past_deadline(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await db.commit()
    run_id = run.id
    expired = await repo.expire_runs(
        deadline=timedelta(minutes=90), now=NOW + timedelta(minutes=91)
    )
    await db.commit()
    db.expire_all()
    assert expired == [run_id]
    run_row = (await db.execute(select(ScanRun).where(ScanRun.id == run_id))).scalar_one()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert run_row.status == "partial" and job.status == "failed" and job.error == "deadline"


async def test_retrying_job_keeps_run_open(db: AsyncSession) -> None:
    # Job đang chờ arq retry chưa phải trạng thái cuối: không được chốt run.
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(i, date(2026, 9, 24), 30) for i in ids])
    assert run is not None
    await repo.finish_job(run.id, ids[0], "retrying", NOW, "calendar timeout")
    await repo.finish_job(run.id, ids[1], "done", NOW)
    assert await repo.try_finish_run(run.id, NOW) is False
    assert (await repo.get_run(run.id)).status == "running"


async def test_run_is_finalized_only_once(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    run_id = run.id
    await repo.finish_job(run_id, ids[0], "failed", NOW, "boom")
    assert await repo.try_finish_run(run_id, NOW) is True
    assert await repo.try_finish_run(run_id, NOW + timedelta(minutes=5)) is False
    await db.commit()
    db.expire_all()
    row = await repo.get_run(run_id)
    assert row.status == "partial" and row.finished_at == NOW


async def test_expire_runs_fails_retrying_jobs(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await repo.finish_job(run.id, ids[0], "retrying", NOW, "calendar timeout")
    await db.commit()
    run_id = run.id
    assert await repo.expire_runs(timedelta(minutes=90), NOW + timedelta(minutes=91)) == [run_id]
    await db.commit()
    db.expire_all()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert job.status == "failed" and job.error == "deadline"
    assert (await repo.get_run(run_id)).status == "partial"


async def test_start_job_skips_jobs_of_closed_run(db: AsyncSession) -> None:
    # Retry arq tới sau khi run đã chốt (hết hạn): không quét lại cho run đã đóng.
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await repo.finish_job(run.id, ids[0], "retrying", NOW, "calendar timeout")
    await db.commit()
    run_id = run.id
    await repo.expire_runs(timedelta(minutes=90), NOW + timedelta(minutes=91))
    await db.commit()
    assert await repo.start_job(run_id, ids[0], NOW + timedelta(minutes=92)) is None


async def test_concurrent_last_jobs_still_finalize_run(db: AsyncSession) -> None:
    # Hai job cuối xong cùng lúc: mỗi transaction thấy job kia còn chạy (READ COMMITTED).
    # Khoá dòng run khi chốt để transaction sau thấy kết quả của transaction trước.
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(i, date(2026, 9, 24), 30) for i in ids])
    assert run is not None
    for i in ids:
        await repo.start_job(run.id, i, NOW)
    await db.commit()
    run_id = run.id
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    async with factory() as a, factory() as b:
        ra, rb = ScanRunRepository(a), ScanRunRepository(b)
        await ra.finish_job(run_id, ids[0], "done", NOW)
        first = await ra.try_finish_run(run_id, NOW)
        await rb.finish_job(run_id, ids[1], "done", NOW)
        second_task = asyncio.create_task(rb.try_finish_run(run_id, NOW))
        await asyncio.sleep(0.5)
        await a.commit()
        second = await asyncio.wait_for(second_task, timeout=10)
        await b.commit()
    assert (first, second) == (False, True)


async def test_probe_stats_since(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    for i, status in enumerate(["ok", "ok", "blocked", "skipped_calendar"]):
        db.add(
            Probe(
                scan_run_id=run.id,
                hotel_id=ids[0],
                stay_date=date(2026, 10, 1) + timedelta(days=i),
                checkin=date(2026, 10, 1),
                checkout=date(2026, 10, 2),
                nights=1,
                adults=2,
                status=status,
                fetched_at=NOW,
            )
        )
    await db.flush()
    total, blocked = await repo.probe_stats_since(NOW - timedelta(minutes=15))
    assert (total, blocked) == (3, 1)  # skipped_calendar không tính vì không phải request


async def test_stale_queued_jobs(db: AsyncSession) -> None:
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(i, date(2026, 9, 24), 30) for i in ids])
    assert run is not None
    await repo.start_job(run.id, ids[0], NOW)
    await db.flush()
    assert await repo.stale_queued_jobs(NOW + timedelta(minutes=6)) == [(run.id, ids[1])]
    assert await repo.stale_queued_jobs(NOW - timedelta(minutes=1)) == []
