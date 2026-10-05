"""Lịch thị trường toàn thành phố: quét danh sách 03:00, run chi tiết 05:00 (giờ tenant), idempotent
và bù khi scheduler lỡ giờ; run thị trường đẩy job dần và có hạn chót riêng."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.db.models import Hotel, ScanJob, ScanRun, Tenant
from app.marketscan import scheduling
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan
from app.marketscan.scheduling import MarketScheduler, market_trigger_key
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.scheduler.channel_pause import MemoryChannelPauses
from app.scheduler.service import SchedulerService
from tests.integration.seed import add_hotel

DAY = date(2026, 10, 3)  # ngày địa phương (Asia/Ho_Chi_Minh, UTC+7)


def local(hh: int, mm: int = 0, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=UTC) - timedelta(hours=7)


class FakeQueue:
    def __init__(self, fail_lists: bool = False) -> None:
        self.probes: list[tuple[int, int]] = []
        self.lists: list[int] = []
        self.list_jobs: list[tuple[int, str | None, int, int | None]] = []
        self.fail_lists = fail_lists

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int, channel: str) -> None:
        self.probes.append((scan_run_id, hotel_id))

    async def enqueue_market_list(
        self,
        area_id: int,
        channel: str,
        start: str | None = None,
        index: int = 0,
        round_ts: int | None = None,
    ) -> None:
        if self.fail_lists:
            raise ConnectionError("redis down")
        self.lists.append(area_id)
        self.list_jobs.append((area_id, start, index, round_ts))


async def _seed(db: AsyncSession, max_hotels: int = 2) -> tuple[MarketArea, list[int]]:
    t = Tenant(
        name="Rex",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(t)
    await db.flush()
    area = MarketArea(
        tenant_id=t.id,
        channel="booking",
        name="HCMC",
        dest_id="-3730078",
        dest_type="city",
        country_code="vn",
        list_nights=14,
        detail_horizon_days=45,
        detail_max_hotels=max_hotels,
        max_pages=60,
        active=True,
    )
    db.add(area)
    await db.flush()
    ids: list[int] = []
    # (review_count, trạng thái listing, thấy lần cuối cách đây bao nhiêu ngày)
    for i, (reviews, status, age) in enumerate(
        [(10, "active", 1), (5000, "active", 1), (300, "active", 1), (9999, "suggested", 1),
         (8000, "active", 20), (None, "active", 1)]
    ):  # fmt: skip
        h = await add_hotel(db, f"vn/h{i}", status=status)
        h.review_count = reviews
        db.add(
            MarketAreaHotel(
                area_id=area.id,
                hotel_id=h.id,
                first_seen_at=local(3, day=DAY - timedelta(days=age)),
                last_seen_at=local(3, day=DAY - timedelta(days=age)),
                best_rank=i + 1,
            )
        )
        ids.append(h.id)
    await db.commit()
    return area, ids


def _sched(db: AsyncSession, queue: FakeQueue, **kw: object) -> MarketScheduler:
    sf = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return MarketScheduler(sf, queue, **kw)  # type: ignore[arg-type]


async def test_daily_list_scan_once_per_local_day_with_catch_up(db: AsyncSession) -> None:
    area, _ = await _seed(db, max_hotels=0)
    queue = FakeQueue()
    sched = _sched(db, queue)
    assert (await sched.tick(local(2, 59))).list_enqueued == []
    assert (await sched.tick(local(3, 0))).list_enqueued == [area.id]
    ts = int(local(3, 0).timestamp())
    assert queue.list_jobs == [(area.id, "2026-10-03", 0, ts)]  # vòng mới: đêm đầu, mã vòng
    await db.refresh(area)
    assert area.last_list_status == "queued"
    assert (await sched.tick(local(3, 1))).list_enqueued == []
    assert (await sched.tick(local(23, 59))).list_enqueued == []
    # Ngày sau: scheduler tắt từ 02:00 tới 11:00 → tick đầu tiên vẫn quét bù.
    next_day = DAY + timedelta(days=1)
    assert (await sched.tick(local(11, 0, next_day))).list_enqueued == [area.id]
    assert queue.list_jobs[-1] == (
        area.id,
        "2026-10-04",
        0,
        int(local(11, 0, next_day).timestamp()),
    )
    await db.refresh(area)
    assert area.list_requested_at == local(11, 0, next_day)


async def test_manual_request_after_slot_counts_for_the_day(db: AsyncSession) -> None:
    area, _ = await _seed(db, max_hotels=0)
    await db.execute(
        update(MarketArea).where(MarketArea.id == area.id).values(list_requested_at=local(3, 30))
    )
    await db.commit()
    queue = FakeQueue()
    assert (await _sched(db, queue).tick(local(4, 0))).list_enqueued == []


async def test_detail_run_top_hotels_by_reviews_once_per_day_and_fed_gradually(
    db: AsyncSession,
) -> None:
    area, ids = await _seed(db, max_hotels=2)
    # h1 (5000 review) đã được quét hôm nay trong run thường → nhường chỗ cho khách sạn kế tiếp.
    repo = ScanRunRepository(db)
    regular = await repo.create_run("2026-10-02T18:00:booking", local(1), [], "booking")
    assert regular is not None
    db.add(
        ScanJob(
            scan_run_id=regular.id,
            hotel_id=ids[1],
            start_date=DAY,
            horizon_days=30,
            status="done",
        )
    )
    await db.commit()
    queue = FakeQueue()
    sched = _sched(db, queue, inflight=1)

    assert (await sched.tick(local(4, 59))).detail_runs == []
    report = await sched.tick(local(5, 0))
    assert len(report.detail_runs) == 1
    run = (
        await db.execute(select(ScanRun).where(ScanRun.id == report.detail_runs[0]))
    ).scalar_one()
    assert run.trigger_key == market_trigger_key(area.id, DAY) == f"market:{area.id}:20261003"
    assert (run.channel, run.status, run.total_jobs) == ("booking", "running", 2)
    jobs = (await db.execute(select(ScanJob).where(ScanJob.scan_run_id == run.id))).scalars().all()
    # 9999 review (listing chỉ là gợi ý) và 8000 (không còn trong danh sách 20 ngày) bị loại.
    assert {j.hotel_id for j in jobs} == {ids[2], ids[0]}
    assert {(j.start_date, j.horizon_days) for j in jobs} == {(DAY, 45)}
    assert queue.probes == [(run.id, ids[2])]  # chỉ 1 job chờ (inflight), nhiều review trước

    second = await sched.tick(local(5, 1))
    assert second.detail_runs == [] and second.topped_up == 1
    assert queue.probes[-1] == (run.id, ids[2])  # job cũ còn chờ: đẩy lại vô hại (trùng _job_id)
    await db.execute(
        update(ScanJob)
        .where(ScanJob.scan_run_id == run.id, ScanJob.hotel_id == ids[2])
        .values(status="running")
    )
    await db.commit()
    await sched.tick(local(5, 2))
    assert queue.probes[-1] == (run.id, ids[0])
    await db.refresh(area)
    assert (area.last_detail_run_id, area.last_detail_scan_at) == (run.id, local(5, 0))


async def test_paused_channel_skips_market_work(db: AsyncSession) -> None:
    await _seed(db)
    pauses = MemoryChannelPauses(lambda: local(5, 30))
    await pauses.pause("booking", 60, "test")
    queue = FakeQueue()
    report = await _sched(db, queue, paused=pauses.is_paused).tick(local(5, 30))
    assert report.list_enqueued == [] and report.detail_runs == [] and report.topped_up == 0
    assert queue.lists == [] and queue.probes == []


async def test_scheduler_does_not_mass_requeue_market_jobs_and_uses_long_deadline(
    db: AsyncSession,
) -> None:
    h1 = await add_hotel(db, "vn/a")
    h2 = await add_hotel(db, "vn/b")
    await db.commit()
    repo = ScanRunRepository(db)
    started = local(5)
    plans = [HotelJobPlan(h1.id, DAY, 30), HotelJobPlan(h2.id, DAY, 30)]
    market = await repo.create_run(f"market:1:{DAY:%Y%m%d}", started, plans, "booking")
    normal = await repo.create_run("2026-10-02T22:00:booking", started, plans, "booking")
    assert market is not None and normal is not None
    await db.commit()

    queue = FakeQueue()
    clock = FixedClock(started + timedelta(minutes=10))
    service = SchedulerService(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        queue=queue,
        clock=clock,
        deadline=timedelta(minutes=90),
        alerter=NullAlerter(),
        market_deadline=timedelta(hours=20),
    )
    report = await service.tick()
    # Job "queued" quá 5 phút: run thường được đẩy lại, run thị trường thì không (đẩy dần riêng).
    assert sorted(queue.probes) == [(normal.id, h1.id), (normal.id, h2.id)]

    clock.advance(hours=2)
    report = await service.tick()
    assert report.expired_runs == [normal.id]  # run thường quá 90 phút; run thị trường chưa

    clock.advance(hours=18)
    report = await service.tick()
    assert report.expired_runs == [market.id]
    status = (await db.execute(select(ScanRun.status).where(ScanRun.id == market.id))).scalar_one()
    assert status == "partial"
    hotels = (await db.execute(select(Hotel.id))).scalars().all()
    assert set(hotels) == {h1.id, h2.id}


async def _second_area(db: AsyncSession, area: MarketArea) -> MarketArea:
    other = MarketArea(
        tenant_id=area.tenant_id,
        channel="booking",
        name="District 1",
        dest_id="2088",
        dest_type="district",
        country_code="vn",
        list_nights=3,
        detail_horizon_days=30,
        detail_max_hotels=0,
        max_pages=10,
        active=True,
    )
    db.add(other)
    await db.commit()
    return other


async def test_enqueue_failure_releases_claim_and_other_areas_still_run(db: AsyncSession) -> None:
    area, _ = await _seed(db, max_hotels=0)
    other = await _second_area(db, area)
    report = await _sched(db, FakeQueue(fail_lists=True)).tick(local(3, 5))
    assert report.failed_areas == [area.id, other.id] and report.list_enqueued == []
    for a in (area, other):
        await db.refresh(a)
        assert a.list_requested_at is None and a.last_list_status is None  # trả lại chốt
    # Redis hồi lại: tick sau trong ngày vẫn mở được vòng cho cả hai khu vực.
    queue = FakeQueue()
    assert (await _sched(db, queue).tick(local(3, 6))).list_enqueued == [area.id, other.id]


async def test_stalled_chain_is_resumed_from_first_unscanned_night(db: AsyncSession) -> None:
    area, _ = await _seed(db, max_hotels=0)
    requested = local(3, 0)
    area.list_nights, area.list_requested_at = 3, requested
    area.last_list_status, area.last_list_scan_at = "running", local(3, 10)
    db.add(
        MarketListScan(area_id=area.id, stay_date=DAY, scanned_at=local(3, 5), status="completed")
    )
    await db.commit()
    queue = FakeQueue()
    sched = _sched(db, queue)
    assert (await sched.tick(local(4, 0))).recovered == []  # chưa quá 2 giờ
    report = await sched.tick(local(5, 30))
    assert report.recovered == [area.id] and report.list_enqueued == []
    assert queue.list_jobs == [(area.id, "2026-10-03", 1, int(requested.timestamp()))]
    await db.refresh(area)
    assert (area.last_list_status, area.last_list_scan_at) == ("queued", local(5, 30))
    assert (await sched.tick(local(5, 31))).recovered == []  # mốc đã đặt lại
    # Mọi đêm đã quét mà trạng thái vẫn "running": chốt "completed", không đẩy gì.
    for i in (1, 2):
        db.add(
            MarketListScan(
                area_id=area.id,
                stay_date=DAY + timedelta(days=i),
                scanned_at=local(6),
                status="error",
            )
        )
    await db.commit()
    assert (await sched.tick(local(8, 0))).recovered == []
    await db.refresh(area)
    assert area.last_list_status == "completed" and len(queue.list_jobs) == 1


async def test_market_list_pause_skips_list_but_not_detail(db: AsyncSession) -> None:
    area, _ = await _seed(db)
    pauses = MemoryChannelPauses(lambda: local(5, 30))
    await pauses.pause("booking:market", 30, "list blocked")
    queue = FakeQueue()
    report = await _sched(db, queue, paused=pauses.is_paused, max_hotels=1).tick(local(5, 30))
    assert report.list_enqueued == [] and queue.lists == []
    assert len(report.detail_runs) == 1
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.total_jobs == 1  # kẹp theo trần MARKET_MAX_HOTELS của scheduler


async def test_idle_detail_is_not_requeried_every_tick(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(db, max_hotels=0)
    t = (await db.execute(select(Tenant.id))).scalar_one()
    empty = MarketArea(
        tenant_id=t,
        channel="booking",
        name="Empty",
        dest_id="1",
        dest_type="district",
        country_code="vn",
        list_nights=1,
        detail_horizon_days=30,
        detail_max_hotels=10,
        max_pages=5,
        active=True,
        list_requested_at=local(3),
    )
    db.add(empty)
    await db.commit()
    calls: list[int] = []
    real = scheduling.detail_candidates

    async def counting(s: AsyncSession, area: MarketArea, seen_since: datetime) -> list[int]:
        calls.append(area.id)
        return await real(s, area, seen_since)

    monkeypatch.setattr(scheduling, "detail_candidates", counting)
    sched = _sched(db, FakeQueue())
    await sched.tick(local(5, 0))
    await sched.tick(local(5, 1))
    await sched.tick(local(5, 20))
    assert calls == [empty.id]  # không có gì để quét: chờ 30 phút mới hỏi lại
    await sched.tick(local(5, 31))
    assert calls == [empty.id, empty.id]


async def test_stuck_list_scans_marked_error_and_old_scans_purged(db: AsyncSession) -> None:
    area, ids = await _seed(db, max_hotels=0)
    stuck = MarketListScan(area_id=area.id, stay_date=DAY, scanned_at=local(1), status="running")
    fresh = MarketListScan(
        area_id=area.id, stay_date=DAY, scanned_at=local(3, 50), status="running"
    )
    old = MarketListScan(
        area_id=area.id,
        stay_date=DAY - timedelta(days=200),
        scanned_at=local(3, day=DAY - timedelta(days=200)),
        status="completed",
    )
    db.add_all([stuck, fresh, old])
    await db.flush()
    db.add(MarketListPrice(scan_id=old.id, hotel_id=ids[0], rank=1))
    await db.commit()
    await _sched(db, FakeQueue(), retention_days=120).tick(local(4, 0))
    rows = {
        sid: (st, err)
        for sid, st, err in await db.execute(
            select(MarketListScan.id, MarketListScan.status, MarketListScan.error)
        )
    }
    assert rows == {stuck.id: ("error", "error: stuck"), fresh.id: ("running", None)}
    assert (await db.execute(select(MarketListPrice))).first() is None  # xoá theo cascade
