from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.config import Settings
from app.db.models import Insight, ListingDemandSignal, OwnHotelDaily, Tenant, TenantHotel
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.insight.client import FakeInsightClient
from app.insight.input_builder import build_input
from app.insight.service import InsightService, due_daily_tenants
from app.repo.snapshots import SnapshotRepository
from tests.integration.conftest import FakeQueue
from tests.integration.seed import add_hotel, scan_run
from tests.integration.test_api import _login
from tests.integration.test_api import _seed as _seed_api

T0 = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)  # 06:00 VN ngày 04/10
STAY = date(2026, 10, 5)
SETTINGS = Settings(
    _env_file=None,
    database_url="x",
    redis_url="x",
    proxy_url_template="x",
    openrouter_model="gpt-6-luna",
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
    db.add(tenant)
    own = await add_hotel(db, "vn/own", name="Own", channels=("booking", "agoda"))
    comp = await add_hotel(db, "vn/comp", name="Comp", channels=("booking", "agoda"))
    db.add_all(
        [
            TenantHotel(tenant_id=tenant.id, hotel_id=own.id, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=comp.id, role="competitor", active=True),
        ]
    )
    run1 = scan_run("r1:booking", T0 - timedelta(hours=8), finished_at=T0 - timedelta(hours=7))
    run2 = scan_run("r2:booking", T0, finished_at=T0 + timedelta(minutes=30))
    run1.total_probes = run2.total_probes = 2
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
    await repo.write_probe(
        run1.id, own.id, "booking", STAY, ok_a, None, "1", "vn", T0 - timedelta(hours=8)
    )
    await repo.write_probe(
        run1.id, comp.id, "booking", STAY, ok_a, None, "1", "vn", T0 - timedelta(hours=8)
    )
    await repo.write_probe(run2.id, own.id, "booking", STAY, ok_a, None, "1", "vn", T0)
    await repo.write_probe(run2.id, comp.id, "booking", STAY, ok_b, None, "1", "vn", T0)
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
    # Giá: chỉ sự kiện mức khách sạn (price_up của loại phòng bị bỏ, tránh lặp cùng biến động).
    types = sorted(e["type"] for e in p["events_24h"])
    assert types == ["low_stock_enter", "price_up", "rooms_decrease"]
    assert next(e for e in p["events_24h"] if e["type"] == "price_up")["room_type"] is None
    assert all(
        e["ref"].startswith("evt:") and e["ref"] in built.valid_refs for e in p["events_24h"]
    )
    assert p["events_7d"] == []  # mọi sự kiện đều trong 24h: không gửi lần hai ở 7d
    assert p["compset"][1]["competitors_sold_out"] == 0 and "compset:2026-10-05" in built.valid_refs
    assert p["data_quality"]["hotel_dates_observed"] == 2 and p["data_quality"]["has_pms_data"]
    assert p["data_quality"]["hotels_omitted"] == 0
    assert built.hotel_ids == {own, comp} and built.scan_run_id is not None
    assert "html" not in str(p).lower()
    assert p["reference_channel"] == "booking" and p["demand_signals"] == []
    assert {e["channel"] for e in p["events_24h"]} == {"booking"}


async def test_build_input_event_windows_are_disjoint(db: AsyncSession) -> None:
    tenant, _, _ = await _seed(db)
    # 25 giờ sau lần quét: sự kiện rời khỏi cửa sổ 24h và chỉ xuất hiện ở 7d.
    p = (await build_input(db, tenant, now=T0 + timedelta(hours=25))).payload
    assert p["events_24h"] == []
    assert sorted(e["type"] for e in p["events_7d"]) == [
        "low_stock_enter",
        "price_up",
        "rooms_decrease",
    ]
    # 8 ngày sau: ra khỏi cả hai cửa sổ.
    p = (await build_input(db, tenant, now=T0 + timedelta(days=8))).payload
    assert p["events_24h"] == [] and p["events_7d"] == []


async def test_build_input_caps_hotels_own_first(db: AsyncSession) -> None:
    tenant, own, comp = await _seed(db)
    built = await build_input(db, tenant, now=T0 + timedelta(hours=1), max_hotels=1)
    p = built.payload
    assert [h["hotel_id"] for h in p["hotels"]] == [own] and built.hotel_ids == {own}
    assert p["data_quality"]["hotels_omitted"] == 1
    assert f"metric:{comp}:2026-10-05" not in built.valid_refs
    assert p["events_24h"] == []  # mọi sự kiện trong seed là của đối thủ bị bỏ


async def test_build_input_uses_reference_channel_and_demand_signals(db: AsyncSession) -> None:
    tenant, own, comp = await _seed(db)
    # Agoda: đối thủ hết phòng, giá khác. Bản tin chỉ lấy ô chỉ số của kênh tham chiếu.
    agoda = scan_run("r3:agoda", T0, channel="agoda", finished_at=T0 + timedelta(minutes=20))
    agoda.total_probes = 1
    db.add(agoda)
    await db.flush()
    sold_out = ProbeResult(
        ProbeStatus.SOLD_OUT, ProbeMethod.HTTP, STAY, STAY + timedelta(days=1), 1, 2, (),
        "<html/>", 200, "s", 10,
    )  # fmt: skip
    await SnapshotRepository(db, 10).write_probe(
        agoda.id, comp, "agoda", STAY, sold_out, None, "1", "vn", T0
    )
    signal = ListingDemandSignal(
        hotel_id=comp,
        channel="agoda",
        scan_run_id=agoda.id,
        kind="bookings_24h",
        value=Decimal("13"),
        window_hours=24,
        raw_text="Đặt 13 lần trong 24 giờ qua",
        observed_at=T0,
    )
    db.add(signal)
    tenant.horizon_days = 90
    await db.commit()
    await AnalyticsService(db).run(agoda.id)
    await db.commit()

    built = await build_input(db, tenant, now=T0 + timedelta(hours=1))
    p = built.payload
    # Horizon quét 90 đêm nhưng bản tin gói trong 30 đêm.
    assert p["period"] == {"start": "2026-10-04", "end": "2026-11-02", "days": 30}
    assert all(len(h["days"]) == 30 for h in p["hotels"])
    comp_day = next(d for d in p["hotels"][1]["days"] if d["date"] == "2026-10-05")
    assert comp_day["status"] == "available" and comp_day["min_price"] == 120.0
    assert p["compset"][1]["competitors_sold_out"] == 0
    assert [
        (s["hotel_id"], s["channel"], s["kind"], s["value"], s["text"]) for s in p["demand_signals"]
    ] == [(comp, "agoda", "bookings_24h", 13.0, "Đặt 13 lần trong 24 giờ qua")]
    assert p["demand_signals"][0]["ref"] in built.valid_refs

    tenant.reference_channel = "agoda"
    await db.commit()
    p = (await build_input(db, tenant, now=T0 + timedelta(hours=1))).payload
    comp_day = next(d for d in p["hotels"][1]["days"] if d["date"] == "2026-10-05")
    assert p["reference_channel"] == "agoda" and comp_day["status"] == "sold_out"


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
    row = await svc.generate(tenant.id, trigger="on_demand", now=T0 + timedelta(hours=1))
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
        tenant.id, "on_demand", request_key=f"req{pending.id}", now=T0 + timedelta(hours=1)
    )
    await db.commit()
    assert row.id == pending.id and row.status == "completed"
    assert len((await db.execute(select(Insight))).scalars().all()) == 1


async def test_generate_keeps_demand_signal_evidence(db: AsyncSession) -> None:
    """Hồi quy: bằng chứng `demand:<id>` phải được coi là hợp lệ khi sinh bản tin."""
    tenant, _, comp = await _seed(db)
    signal = ListingDemandSignal(
        hotel_id=comp,
        channel="booking",
        scan_run_id=None,
        kind="bookings_24h",
        value=Decimal("13"),
        window_hours=24,
        raw_text="Đặt 13 lần trong 24 giờ qua",
        observed_at=T0,
    )
    db.add(signal)
    await db.commit()
    client = FakeInsightClient(
        default_output={
            "summary": "x",
            "highlights": [
                {
                    "title": "Comp được đặt nhiều",
                    "date_from": "2026-10-05",
                    "date_to": "2026-10-05",
                    "hotel_ids": [comp],
                    "evidence": [{"kind": "demand", "ref": f"demand:{signal.id}"}],
                    "confidence": "medium",
                    "recommendation": "x",
                }
            ],
            "demand_signals": [],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "",
        }
    )
    row = await InsightService(db, client, SETTINGS).generate(
        tenant.id, "daily", request_key="daily:2026-10-04", now=T0 + timedelta(hours=1)
    )
    assert row.status == "completed" and row.dropped_highlights == []
    assert row.output_json is not None and len(row.output_json["highlights"]) == 1
    assert row.input_json["demand_signals"][0]["ref"] == f"demand:{signal.id}"


async def test_generate_failure_and_empty_watchlist(db: AsyncSession) -> None:
    tenant, _, _ = await _seed(db)
    client = FakeInsightClient()
    client.fail_with = "rate limited"
    row = await InsightService(db, client, SETTINGS).generate(
        tenant.id, "on_demand", now=T0 + timedelta(hours=1)
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
        empty.id, "daily", request_key="daily:2026-10-04", now=T0 + timedelta(hours=1)
    )
    assert row.status == "failed" and row.error == "watchlist is empty"


async def test_daily_generation_is_sync_and_idempotent(db: AsyncSession) -> None:
    """Hằng ngày gọi model đồng bộ y như theo yêu cầu (không còn batch_pending), và cùng
    ngày địa phương thì không sinh bản thứ hai."""
    tenant, _, _ = await _seed(db)
    client = FakeInsightClient(
        default_output={
            "summary": "daily",
            "highlights": [],
            "demand_signals": [],
            "pricing_opportunities": [],
            "risks": [],
            "data_quality_note": "",
        }
    )
    svc = InsightService(db, client, SETTINGS)
    row = await svc.generate(
        tenant.id, "daily", request_key="daily:2026-10-04", now=T0 + timedelta(hours=1)
    )
    await db.commit()
    assert row.status == "completed" and row.trigger == "daily" and row.batch_id is None
    assert row.output_json is not None and row.output_json["summary"] == "daily"
    assert str(row.cost_usd) == "0.003000"
    again = await svc.generate(
        tenant.id, "daily", request_key="daily:2026-10-04", now=T0 + timedelta(hours=2)
    )
    assert again.id == row.id and len(client.requests) == 1
    assert len((await db.execute(select(Insight))).scalars().all()) == 1


# ---- API: /insights ----


def _insight_row(tenant_id: int, status: str, error: str | None, at: datetime) -> Insight:
    return Insight(
        tenant_id=tenant_id,
        period_start=at.date(),
        period_end=at.date() + timedelta(days=29),
        generated_at=at,
        trigger="on_demand",
        status=status,
        model="m",
        prompt_version="1",
        input_json={},
        output_json=None,
        dropped_highlights=[],
        error=error,
    )


async def test_generate_api_dedups_and_survives_duplicate_pending_rows(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed_api(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/insights/generate")
    assert r.status_code == 202, r.text
    first = r.json()
    r = await client.post("/insights/generate")
    assert r.status_code == 202 and r.json()["id"] == first["id"]
    assert len(queue.insights) == 1
    # Hai dòng pending đã lọt (đua trước khi có khoá): lần sau trả dòng mới nhất, không 500.
    now = datetime.now(tz=UTC)
    db.add_all([_insight_row(ids["t1"], "pending", None, now) for _ in range(2)])
    await db.commit()
    newest = max(
        (await db.execute(select(Insight.id).where(Insight.tenant_id == ids["t1"]))).scalars()
    )
    r = await client.post("/insights/generate")
    assert r.status_code == 202 and r.json()["id"] == newest
    assert len(queue.insights) == 1
    assert len((await db.execute(select(Insight))).scalars().all()) == 3


async def test_insight_error_is_short_code_for_tenant_users(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed_api(db)
    now = datetime.now(tz=UTC)
    rows = [
        _insight_row(ids["t1"], "failed", "schema: 1 validation error for InsightOutput", now),
        _insight_row(ids["t1"], "failed", "no scan data yet (no scan/analytics data)", now),
        _insight_row(ids["t1"], "failed", "APIConnectionError: Connection error.", now),
        _insight_row(ids["t1"], "completed", None, now),
    ]
    db.add_all(rows)
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.get("/insights")
    assert r.status_code == 200
    by_id = {x["id"]: x["error"] for x in r.json()}
    assert [by_id[x.id] for x in rows] == [
        "schema_invalid",
        "no_scan_data",
        "provider_error",
        None,
    ]
    r = await client.get(f"/insights/{rows[2].id}")
    assert r.status_code == 200 and r.json()["error"] == "provider_error"
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get("/insights", params={"tenant_id": ids["t1"]})
    by_id = {x["id"]: x["error"] for x in r.json()}
    assert by_id[rows[2].id] == "APIConnectionError: Connection error."
    r = await client.get(f"/insights/{rows[0].id}", params={"tenant_id": ids["t1"]})
    assert r.json()["error"] == "schema: 1 validation error for InsightOutput"


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
