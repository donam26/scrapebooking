from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.config import Settings
from app.db.models import Hotel, Insight, OwnHotelDaily, ScanRun, Tenant, TenantHotel
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.insight.client import FakeInsightClient
from app.insight.input_builder import build_input
from app.insight.service import InsightService, due_daily_tenants
from app.repo.snapshots import SnapshotRepository

T0 = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)  # 06:00 VN ngày 04/10
STAY = date(2026, 10, 5)
SETTINGS = Settings(
    _env_file=None,
    database_url="x",
    redis_url="x",
    proxy_url_template="x",
    openai_model="gpt-6-luna",
)


def _offer(rid: str, badge: int | None, dropdown: int | None, price: str) -> RoomOffer:
    return RoomOffer(
        rid,
        f"Room {rid}",
        2,
        badge,
        dropdown,
        (RatePlan("Std", Decimal(price), "VND", True, None),),
    )


async def _seed(db: AsyncSession) -> tuple[Tenant, int, int]:
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
    own = Hotel(booking_url="u", booking_slug="vn/own", country_code="vn", name="Own")
    comp = Hotel(booking_url="u", booking_slug="vn/comp", country_code="vn", name="Comp")
    db.add_all([tenant, own, comp])
    await db.flush()
    db.add_all(
        [
            TenantHotel(tenant_id=tenant.id, hotel_id=own.id, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=comp.id, role="competitor", active=True),
        ]
    )
    run1 = ScanRun(
        trigger_key="r1",
        scheduled_at=T0 - timedelta(hours=8),
        started_at=T0 - timedelta(hours=8),
        finished_at=T0 - timedelta(hours=7),
        status="completed",
        total_probes=2,
    )
    run2 = ScanRun(
        trigger_key="r2",
        scheduled_at=T0,
        started_at=T0,
        finished_at=T0 + timedelta(minutes=30),
        status="completed",
        total_probes=2,
    )
    db.add_all([run1, run2])
    await db.flush()
    repo = SnapshotRepository(db, 10)
    ok_a = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (_offer("1", 4, 4, "100"),),
        "<html/>",
        200,
        "s",
        10,
    )
    ok_b = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (_offer("1", 1, 1, "120"),),
        "<html/>",
        200,
        "s",
        10,
    )
    await repo.write_probe(run1.id, own.id, STAY, ok_a, None, "1", "vn", T0 - timedelta(hours=8))
    await repo.write_probe(run1.id, comp.id, STAY, ok_a, None, "1", "vn", T0 - timedelta(hours=8))
    await repo.write_probe(run2.id, own.id, STAY, ok_a, None, "1", "vn", T0)
    await repo.write_probe(run2.id, comp.id, STAY, ok_b, None, "1", "vn", T0)
    db.add(
        OwnHotelDaily(
            tenant_id=tenant.id,
            hotel_id=own.id,
            stay_date=STAY,
            rooms_total=50,
            rooms_sold=30,
            rooms_available=20,
            occupancy_pct=Decimal("60"),
            source="csv",
            imported_at=T0,
        )
    )
    await db.commit()
    await AnalyticsService(db).run(run1.id)
    await AnalyticsService(db).run(run2.id)
    await db.commit()
    return tenant, own.id, comp.id


async def test_build_input_shape_and_refs(db: AsyncSession) -> None:
    tenant, own, comp = await _seed(db)
    built = await build_input(db, tenant, now=T0 + timedelta(hours=1))
    p = built.payload
    assert p["period"] == {"start": "2026-10-04", "end": "2026-11-02", "days": 30}
    assert [h["role"] for h in p["hotels"]] == ["self", "competitor"]
    own_day = next(d for d in p["hotels"][0]["days"] if d["date"] == "2026-10-05")
    assert own_day["status"] == "available" and own_day["rooms_left_exact"] == 4
    assert own_day["pms"]["occupancy_pct"] == 60.0
    comp_day = next(d for d in p["hotels"][1]["days"] if d["date"] == "2026-10-05")
    assert comp_day["rooms_left_exact"] == 1 and comp_day["min_price"] == 120.0
    assert f"metric:{comp}:2026-10-05" in built.valid_refs
    assert (
        next(d for d in p["hotels"][0]["days"] if d["date"] == "2026-10-06")["status"] == "no_data"
    )
    types = sorted(e["type"] for e in p["events_24h"])
    assert types == ["low_stock_enter", "price_up", "price_up", "rooms_decrease"]
    assert all(
        e["ref"].startswith("evt:") and e["ref"] in built.valid_refs for e in p["events_24h"]
    )
    assert p["compset"][1]["competitors_sold_out"] == 0 and "compset:2026-10-05" in built.valid_refs
    assert p["data_quality"]["hotel_dates_observed"] == 2 and p["data_quality"]["has_pms_data"]
    assert built.hotel_ids == {own, comp} and built.scan_run_id is not None
    assert "html" not in str(p).lower()


async def test_generate_sync_validates_and_stores(db: AsyncSession) -> None:
    tenant, own, comp = await _seed(db)
    built = await build_input(db, tenant, now=T0 + timedelta(hours=1))
    evt_ref = next(iter(r for r in built.valid_refs if r.startswith("evt:")))
    client = FakeInsightClient(
        default_output={
            "summary": "Đối thủ Comp còn 1 phòng ngày 05/10.",
            "highlights": [
                {
                    "title": "Comp sắp hết phòng",
                    "date_from": "2026-10-05",
                    "date_to": "2026-10-05",
                    "hotel_ids": [comp],
                    "evidence": [{"kind": "event", "ref": evt_ref}],
                    "confidence": "high",
                    "recommendation": "Tăng giá",
                },
                {
                    "title": "Bịa",
                    "date_from": "2026-10-05",
                    "date_to": "2026-10-05",
                    "hotel_ids": [comp],
                    "evidence": [{"kind": "event", "ref": "evt:404"}],
                    "confidence": "low",
                    "recommendation": "x",
                },
            ],
            "demand_signals": [
                {"date": "2026-10-05", "level": "high", "reason": "đối thủ sắp hết"}
            ],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "ok",
        }
    )
    svc = InsightService(db, client=client, settings=SETTINGS)
    row = await svc.generate(
        tenant.id, trigger="on_demand", use_batch=False, now=T0 + timedelta(hours=1)
    )
    await db.commit()
    assert row.status == "completed" and row.trigger == "on_demand"
    assert row.output_json is not None and len(row.output_json["highlights"]) == 1
    assert (
        len(row.dropped_highlights) == 1
        and "unknown refs" in row.dropped_highlights[0]["reasons"][0]
    )
    assert row.tokens_in == 20_000 and str(row.cost_usd) == "0.003000"
    assert row.input_json["language"] == "vi" and row.scan_run_id is not None
    assert client.requests[0].custom_id == f"insight-{row.id}"


async def test_generate_fills_pending_row_from_api(db: AsyncSession) -> None:
    tenant, _, _ = await _seed(db)
    pending = Insight(
        tenant_id=tenant.id,
        period_start=STAY,
        period_end=STAY,
        generated_at=T0,
        trigger="on_demand",
        status="pending",
        model="m",
        prompt_version="1",
        input_json={},
        output_json=None,
        dropped_highlights=[],
    )
    db.add(pending)
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
    row = await InsightService(db, client, SETTINGS).generate(
        tenant.id,
        "on_demand",
        use_batch=False,
        request_key=f"req{pending.id}",
        now=T0 + timedelta(hours=1),
    )
    await db.commit()
    assert row.id == pending.id and row.status == "completed"
    assert len((await db.execute(select(Insight))).scalars().all()) == 1


async def test_generate_failure_and_empty_watchlist(db: AsyncSession) -> None:
    tenant, _, _ = await _seed(db)
    client = FakeInsightClient()
    client.fail_with = "rate limited"
    row = await InsightService(db, client, SETTINGS).generate(
        tenant.id, "on_demand", use_batch=False, now=T0 + timedelta(hours=1)
    )
    assert row.status == "failed" and row.error == "rate limited"
    empty = Tenant(
        name="E",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(empty)
    await db.commit()
    row = await InsightService(db, client, SETTINGS).generate(
        empty.id, "daily", use_batch=True, now=T0 + timedelta(hours=1)
    )
    assert row.status == "failed" and row.error == "watchlist is empty"


async def test_batch_flow_and_daily_idempotency(db: AsyncSession) -> None:
    tenant, _, comp = await _seed(db)
    client = FakeInsightClient(
        default_output={
            "summary": "batch",
            "highlights": [],
            "demand_signals": [],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "",
        }
    )
    client.batch_status = "in_progress"
    svc = InsightService(db, client, SETTINGS)
    row = await svc.generate(
        tenant.id,
        "daily",
        use_batch=True,
        request_key="daily:2026-10-04",
        now=T0 + timedelta(hours=1),
    )
    await db.commit()
    assert row.status == "batch_pending" and row.batch_id == "batch_1"
    # cùng ngày gọi lại: không tạo bản mới
    again = await svc.generate(
        tenant.id,
        "daily",
        use_batch=True,
        request_key="daily:2026-10-04",
        now=T0 + timedelta(hours=2),
    )
    row_id = row.id
    assert again.id == row_id and len(client.batches) == 1
    assert await svc.poll_batches() == 0  # chưa xong
    client.batch_status = "completed"
    assert await svc.poll_batches() == 1
    await db.commit()
    db.expire_all()
    done = (await db.execute(select(Insight).where(Insight.id == row_id))).scalar_one()
    assert done.status == "completed" and done.output_json["summary"] == "batch"
    assert str(done.cost_usd) == "0.001500"  # giảm 50% cho batch


def test_due_daily_tenants_local_time() -> None:
    t = Tenant(
        id=1,
        name="A",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    now = datetime(2026, 10, 4, 0, 33, tzinfo=UTC)  # 07:33 VN
    due = due_daily_tenants([t], now, timedelta(minutes=10))
    assert [(d.tenant_id, d.request_key) for d in due] == [(1, "daily:2026-10-04")]
    assert (
        due_daily_tenants([t], datetime(2026, 10, 4, 0, 45, tzinfo=UTC), timedelta(minutes=10))
        == []
    )
