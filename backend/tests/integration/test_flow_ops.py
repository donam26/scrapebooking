"""Flow F: vận hành scraper — quét ngay, run hết hạn đẩy analytics, retry job, dispatch bản tin."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from arq import Retry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.fake import FakeCollector
from app.collector.storage import MemoryRawStore
from app.config import Settings
from app.db.models import Hotel, Insight, ScanJob, ScanRun, Tenant, TenantHotel
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.insight.client import FakeInsightClient
from app.insight.service import InsightService, daily_due_today
from app.jobs.settings import select_daily_dispatch
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.repo.snapshots import SnapshotRepository
from app.scheduler.service import SchedulerService
from app.worker.jobs import WorkerDeps
from app.worker.settings import MAX_TRIES, probe_hotel
from tests.integration.conftest import FakeQueue
from tests.integration.test_api import _login, _seed

NOW = datetime(2026, 9, 23, 23, 2, tzinfo=UTC)


class FakeSchedulerQueue(FakeQueue):
    pass


# ---- quét ngay ----


async def test_tenant_scan_now_creates_run_and_dedups(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    await _login(client, "view@a.com", "view-pass-1")
    assert (await client.post("/watchlist/scan-now")).status_code == 403
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/watchlist/scan-now")
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["total_jobs"] == 2 and run["trigger_key"].startswith(f"manual:t{ids['t1']}:")
    assert sorted(queue.probes) == sorted([(run["id"], ids["own"]), (run["id"], ids["comp"])])
    # gọi lại trong 10 phút: trả đợt đang chạy, không tạo thêm
    r2 = await client.post("/watchlist/scan-now")
    assert r2.status_code == 202 and r2.json()["id"] == run["id"]
    assert len(queue.probes) == 2
    # tenant khác không nhìn thấy khách sạn của t1 trong đợt của mình
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post("/watchlist/scan-now", params={"tenant_id": ids["t2"]})
    assert r.status_code == 202 and r.json()["total_jobs"] == 1
    r = await client.post("/health/scan-now")
    assert r.status_code == 202 and r.json()["total_jobs"] == 3


async def test_scan_now_empty_watchlist_is_422(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client, "op@x.com", "op-pass-123")
    t = Tenant(
        name="Empty",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(t)
    await db.commit()
    r = await client.post("/watchlist/scan-now", params={"tenant_id": t.id})
    assert r.status_code == 422 and "empty" in r.json()["detail"]


# ---- run hết hạn -> analytics ----


async def test_expired_run_is_sent_to_analytics(db: AsyncSession) -> None:
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
    h1 = Hotel(booking_url="u", booking_slug="vn/h1", country_code="vn")
    db.add_all([t1, h1])
    await db.flush()
    db.add(TenantHotel(tenant_id=t1.id, hotel_id=h1.id, role="self", active=True))
    await db.commit()
    queue = FakeSchedulerQueue()
    clock = FixedClock(NOW)
    svc = SchedulerService(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        queue=queue,
        clock=clock,
        deadline=timedelta(minutes=90),
        alerter=NullAlerter(),
    )
    first = await svc.tick()
    assert len(first.created_runs) == 1
    clock.advance(minutes=95)
    report = await svc.tick()
    assert report.expired_runs == first.created_runs
    assert queue.analytics == first.created_runs


# ---- job probe: retry rồi chốt run ----


def _deps(db: AsyncSession, collector: FakeCollector) -> WorkerDeps:
    return WorkerDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector,
        raw_store=MemoryRawStore(),
        clock=FixedClock(NOW),
        page_cap=10,
        default_adults=2,
        parser_version="1",
        alerter=NullAlerter(),
        worker_id="w1",
    )


async def test_probe_hotel_retries_then_finalizes_run(db: AsyncSession) -> None:
    class BrokenCalendar(FakeCollector):
        async def fetch_calendar(self, hotel, start, days, adults):  # type: ignore[no-untyped-def]
            raise RuntimeError("db gone")

    hotel = Hotel(booking_url="u", booking_slug="vn/h1", country_code="vn")
    db.add(hotel)
    await db.flush()
    run = await ScanRunRepository(db).create_run(
        "k", NOW, [HotelJobPlan(hotel.id, date(2026, 9, 24), 2)]
    )
    assert run is not None
    await db.commit()
    run_id, hotel_id = run.id, hotel.id
    ctx: dict[str, Any] = {"deps": _deps(db, BrokenCalendar()), "job_try": 1}
    with pytest.raises(Retry):
        await probe_hotel(ctx, run_id, hotel_id)
    db.expire_all()
    assert (await db.execute(select(ScanRun))).scalar_one().status == "running"
    ctx["job_try"] = MAX_TRIES
    with pytest.raises(Exception, match="db gone"):
        await probe_hotel(ctx, run_id, hotel_id)
    db.expire_all()
    run_row = (await db.execute(select(ScanRun))).scalar_one()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert run_row.status == "partial" and job.status == "failed"


# ---- bản tin: không có dữ liệu quét ----


async def test_insight_without_scan_data_fails_fast(db: AsyncSession) -> None:
    tenant = Tenant(
        name="T",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    hotel = Hotel(booking_url="u", booking_slug="vn/h", country_code="vn")
    db.add_all([tenant, hotel])
    await db.flush()
    db.add(TenantHotel(tenant_id=tenant.id, hotel_id=hotel.id, role="self", active=True))
    await db.commit()
    client = FakeInsightClient(
        default_output={
            "summary": "x",
            "highlights": [],
            "demand_signals": [],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "",
        }
    )
    settings = Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    row = await InsightService(db, client, settings).generate(
        tenant.id, "on_demand", use_batch=False
    )
    assert row.status == "failed" and "no scan data" in (row.error or "")
    assert client.requests == []  # không tốn token


# ---- dispatch bản tin hằng ngày có catch-up và giới hạn lỗi ----


def _offer() -> RoomOffer:
    return RoomOffer("1", "R", 2, 2, 2, (RatePlan("Std", Decimal("100"), "VND", True, None),))


async def test_daily_dispatch_catch_up_and_failure_cap(db: AsyncSession) -> None:
    tenant = Tenant(
        name="T",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(tenant)
    await db.commit()
    before = datetime(2026, 10, 4, 0, 0, tzinfo=UTC)  # 07:00 VN: chưa tới giờ
    after = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)  # 12:00 VN: đã qua giờ (catch-up)
    assert daily_due_today([tenant], before) == []
    assert await select_daily_dispatch(db, before) == []
    assert await select_daily_dispatch(db, after) == [(tenant.id, "daily:2026-10-04")]
    # đã có bản tin daily hôm nay (batch_pending) -> không đẩy nữa
    row = Insight(
        tenant_id=tenant.id,
        period_start=date(2026, 10, 4),
        period_end=date(2026, 11, 2),
        generated_at=after,
        trigger="daily",
        status="batch_pending",
        model="m",
        prompt_version="1",
        input_json={},
        output_json=None,
        dropped_highlights=[],
    )
    db.add(row)
    await db.commit()
    assert await select_daily_dispatch(db, after) == []
    # 2 lần thất bại -> dừng
    row.status = "failed"
    db.add(
        Insight(
            tenant_id=tenant.id,
            period_start=date(2026, 10, 4),
            period_end=date(2026, 11, 2),
            generated_at=after,
            trigger="daily",
            status="failed",
            model="m",
            prompt_version="1",
            input_json={},
            output_json=None,
            dropped_highlights=[],
        )
    )
    await db.commit()
    assert await select_daily_dispatch(db, after) == []


async def test_daily_dispatch_retries_after_single_failure(db: AsyncSession) -> None:
    tenant = Tenant(
        name="T",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(tenant)
    await db.flush()
    db.add(
        Insight(
            tenant_id=tenant.id,
            period_start=date(2026, 10, 4),
            period_end=date(2026, 11, 2),
            generated_at=NOW,
            trigger="daily",
            status="failed",
            model="m",
            prompt_version="1",
            input_json={},
            output_json=None,
            dropped_highlights=[],
        )
    )
    await db.commit()
    after = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    assert await select_daily_dispatch(db, after) == [(tenant.id, "daily:2026-10-04")]


async def test_snapshot_then_insight_end_to_end_with_manual_run(db: AsyncSession) -> None:
    """Đường đi đầy đủ: run thủ công -> snapshot -> analytics -> insight có dữ liệu."""
    from app.analytics.service import AnalyticsService

    tenant = Tenant(
        name="T",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=3,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    hotel = Hotel(booking_url="u", booking_slug="vn/h", country_code="vn")
    db.add_all([tenant, hotel])
    await db.flush()
    db.add(TenantHotel(tenant_id=tenant.id, hotel_id=hotel.id, role="self", active=True))
    run = await ScanRunRepository(db).create_run(
        "manual:t1:x", NOW, [HotelJobPlan(hotel.id, date(2026, 9, 24), 3)]
    )
    assert run is not None
    await db.commit()
    stay = date(2026, 9, 24)
    res = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        stay,
        stay + timedelta(days=1),
        1,
        2,
        (_offer(),),
        "<html/>",
        200,
        "s",
        10,
    )
    await SnapshotRepository(db, 10).write_probe(run.id, hotel.id, stay, res, None, "1", "vn", NOW)
    await ScanRunRepository(db).finish_job(run.id, hotel.id, "done", NOW)
    assert await ScanRunRepository(db).try_finish_run(run.id, NOW)
    await db.commit()
    await AnalyticsService(db).run(run.id)
    await db.commit()
    client = FakeInsightClient(
        default_output={
            "summary": "ok",
            "highlights": [],
            "demand_signals": [],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "",
        }
    )
    settings = Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    row = await InsightService(db, client, settings).generate(
        tenant.id, "on_demand", use_batch=False, now=NOW + timedelta(hours=1)
    )
    assert row.status == "completed" and row.scan_run_id == run.id
