from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.api.auth import hash_password
from app.db.models import ScanJob, Tenant, TenantHotel, User
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.snapshots import SnapshotRepository
from tests.integration.conftest import FakeQueue
from tests.integration.seed import add_hotel, scan_run

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
STAY = date(2026, 10, 5)


async def _seed(db: AsyncSession) -> dict[str, int]:
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
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add_all([t1, t2])
    own = await add_hotel(db, "vn/own", name="Own Hotel")
    comp = await add_hotel(db, "vn/comp", name="Comp Hotel")
    other = await add_hotel(db, "vn/other")
    db.add_all(
        [
            TenantHotel(tenant_id=t1.id, hotel_id=own.id, role="self", active=True, label="Mine"),
            TenantHotel(tenant_id=t1.id, hotel_id=comp.id, role="competitor", active=True),
            TenantHotel(tenant_id=t2.id, hotel_id=other.id, role="competitor", active=True),
            User(
                tenant_id=None,
                email="op@x.com",
                password_hash=hash_password("op-pass-123"),
                role="operator",
                active=True,
            ),
            User(
                tenant_id=t1.id,
                email="admin@a.com",
                password_hash=hash_password("admin-pass-1"),
                role="tenant_admin",
                active=True,
            ),
            User(
                tenant_id=t1.id,
                email="view@a.com",
                password_hash=hash_password("view-pass-1"),
                role="viewer",
                active=True,
            ),
        ]
    )
    await db.commit()
    return {"t1": t1.id, "t2": t2.id, "own": own.id, "comp": comp.id, "other": other.id}


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text


async def test_login_me_logout_and_bad_password(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    r = await client.post("/auth/login", json={"email": "admin@a.com", "password": "wrong-pass"})
    assert r.status_code == 401
    r = await client.get("/auth/me")
    assert r.status_code == 401
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.get("/auth/me")
    assert r.status_code == 200 and r.json()["role"] == "tenant_admin"
    r = await client.post("/auth/logout")
    assert r.status_code == 204
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_tenant_scoping_and_roles(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    # viewer thấy watchlist của tenant mình, không ghi được
    await _login(client, "view@a.com", "view-pass-1")
    r = await client.get("/watchlist")
    assert r.status_code == 200
    assert _keys(r.json()) == ["vn/own", "vn/comp"]  # self trước
    r = await client.post("/watchlist", json={"url": "https://www.booking.com/hotel/vn/new.html"})
    assert r.status_code == 403
    r = await client.get("/watchlist", params={"tenant_id": ids["t2"]})
    assert r.status_code == 403
    r = await client.get("/tenants")
    assert r.status_code == 403
    r = await client.get("/health/summary")
    assert r.status_code == 403
    # operator phải chỉ định tenant_id
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get("/watchlist")
    assert r.status_code == 400
    r = await client.get("/watchlist", params={"tenant_id": ids["t2"]})
    assert r.status_code == 200 and _keys(r.json()) == ["vn/other"]
    r = await client.get("/tenants")
    assert r.status_code == 200 and len(r.json()) == 2


async def test_watchlist_crud(client: AsyncClient, db: AsyncSession, queue: FakeQueue) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(
        "/watchlist",
        json={
            "url": "https://www.booking.com/hotel/vn/the-reverie-saigon.vi.html?aid=1",
            "role": "competitor",
            "label": "Reverie",
        },
    )
    assert r.status_code == 201, r.text
    hotel_id = r.json()["hotel"]["id"]
    [listing] = r.json()["hotel"]["listings"]
    assert listing["listing_key"] == "vn/the-reverie-saigon" and r.json()["label"] == "Reverie"
    r = await client.post("/watchlist", json={"url": "https://www.booking.com/searchresults.html"})
    assert r.status_code == 422 and "booking.com/hotel/vn" in r.json()["detail"]
    r = await client.post(
        "/watchlist",
        json={"url": "https://www.booking.com/searchresults.html"},
        headers={"Accept-Language": "en-GB,en;q=0.9"},
    )
    assert r.status_code == 422 and r.json()["detail"].startswith("The Booking link must be")
    r = await client.patch(f"/watchlist/{hotel_id}", json={"label": "RV"})
    assert r.status_code == 200 and r.json()["label"] == "RV"
    r = await client.delete(f"/watchlist/{hotel_id}")
    assert r.status_code == 204
    r = await client.get("/watchlist")
    assert hotel_id not in [w["hotel"]["id"] for w in r.json()]
    r = await client.get("/watchlist", params={"include_inactive": "true"})
    assert hotel_id in [w["hotel"]["id"] for w in r.json()]
    r = await client.delete(f"/watchlist/{ids['other']}")
    assert r.status_code == 404


async def test_settings_and_users(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.patch(
        "/settings", json={"scan_times": ["05:00", "13:00"], "insight_hour": "06:30"}
    )
    assert r.status_code == 200 and r.json()["scan_times"] == ["05:00", "13:00"]
    r = await client.patch("/settings", json={"scan_times": ["25:00"]})
    assert r.status_code == 422
    r = await client.patch("/settings", json={"insight_language": "fr"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "insight_language"]
    r = await client.patch("/settings", json={"insight_language": "en"})
    assert r.status_code == 200 and r.json()["insight_language"] == "en"
    r = await client.post(
        "/users", json={"email": "new@a.com", "password": "password-1", "role": "viewer"}
    )
    assert r.status_code == 201 and r.json()["tenant_id"] == ids["t1"]
    r = await client.post(
        "/users", json={"email": "new@a.com", "password": "password-1", "role": "viewer"}
    )
    assert r.status_code == 409
    r = await client.post(
        "/users", json={"email": "op2@a.com", "password": "password-1", "role": "operator"}
    )
    assert r.status_code == 403
    r = await client.get("/users")
    assert {u["email"] for u in r.json()} == {"admin@a.com", "view@a.com", "new@a.com"}
    uid = next(u["id"] for u in r.json() if u["email"] == "new@a.com")
    r = await client.patch(f"/users/{uid}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post("/tenants", json={"name": "C", "scan_times": ["07:00"]})
    assert r.status_code == 201
    r = await client.patch(f"/tenants/{r.json()['id']}", json={"horizon_days": 45})
    assert r.status_code == 200 and r.json()["horizon_days"] == 45


def _keys(items: list[dict[str, object]]) -> list[str]:
    return [w["hotel"]["listings"][0]["listing_key"] for w in items]  # type: ignore[index]


def _offer(rid: str, badge: int | None, dropdown: int | None, price: str) -> RoomOffer:
    return RoomOffer(
        rid,
        f"Room {rid}",
        2,
        badge,
        dropdown,
        (RatePlan("Std", Decimal(price), "VND", True, None),),
    )


async def _snapshot_data(db: AsyncSession, ids: dict[str, int]) -> int:
    run = scan_run("r1:booking", T0, finished_at=T0 + timedelta(minutes=20))
    run.total_probes = 2
    db.add(run)
    await db.flush()
    repo = SnapshotRepository(db, 10)
    ok = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (_offer("1", 2, 2, "100"),),
        "<html/>",
        200,
        "s",
        10,
    )
    await repo.write_probe(run.id, ids["own"], "booking", STAY, ok, None, "1", "vn", T0)
    await repo.write_probe(
        run.id,
        ids["comp"],
        "booking",
        STAY,
        ProbeResult(
            ProbeStatus.SOLD_OUT,
            ProbeMethod.HTTP,
            STAY,
            STAY + timedelta(days=1),
            1,
            2,
            (),
            "<html/>",
            200,
            "s",
            10,
        ),
        None,
        "1",
        "vn",
        T0,
    )
    await db.commit()
    await AnalyticsService(db).run(run.id)
    await db.commit()
    run2 = scan_run("r2:booking", T0 + timedelta(hours=8), finished_at=T0 + timedelta(hours=9))
    run2.total_probes = 2
    db.add(run2)
    await db.flush()
    ok2 = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (_offer("1", 1, 1, "110"),),
        "<html/>",
        200,
        "s",
        10,
    )
    await repo.write_probe(
        run2.id, ids["own"], "booking", STAY, ok2, None, "1", "vn", T0 + timedelta(hours=8)
    )
    await repo.write_probe(
        run2.id, ids["comp"], "booking", STAY, ok, None, "1", "vn", T0 + timedelta(hours=8)
    )
    await db.commit()
    await AnalyticsService(db).run(run2.id)
    await db.commit()
    return run2.id


async def test_overview_hotel_day_events(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    run2 = await _snapshot_data(db, ids)
    await _login(client, "view@a.com", "view-pass-1")

    r = await client.get(
        "/overview",
        params={"start": STAY.isoformat(), "end": (STAY + timedelta(days=2)).isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [h["role"] for h in body["hotels"]] == ["self", "competitor"]
    own_cell = body["hotels"][0]["cells"][0]
    assert own_cell["availability_status"] == "available" and own_cell["exact_rooms_left"] == 1
    assert own_cell["min_price"] == "110.00" and own_cell["pickup_24h"] is None
    comp_cell = body["hotels"][1]["cells"][0]
    assert comp_cell["availability_status"] == "available" and comp_cell["restocked_at"] is not None
    assert body["hotels"][0]["cells"][1]["availability_status"] is None
    # Một đối thủ có giá: dưới ngưỡng cỡ mẫu CoStar STR (≥4) nên không có trung vị/chỉ số/vị trí,
    # nhưng vẫn báo n/N để giao diện ghi "chưa đủ mẫu".
    c0 = body["compset"][0]
    assert c0["competitors_observed"] == 1 and c0["price_index"] is None
    assert (c0["competitors_priced"], c0["competitors_total"], c0["sample"]) == (
        1,
        1,
        "insufficient",
    )
    assert c0["own_rank"] is None and c0["priced_hotels"] == 2 and c0["min_price"] == "100.00"
    assert body["compset"][1]["own_rank"] is None
    assert body["holidays"] == []
    assert body["last_run"]["id"] == run2
    r = await client.get("/overview", params={"start": "2026-09-01", "end": "2026-09-03"})
    # Quốc khánh 2026 nghỉ 29/8–2/9: 1/9 là ngày nghỉ liền kề, 2/9 là ngày lễ.
    assert r.json()["holidays"] == [
        {
            "date": "2026-09-01",
            "name": "Quốc khánh (nghỉ bù)",
            "kind": "holiday",
            "group": "national_day",
        },
        {"date": "2026-09-02", "name": "Quốc khánh", "kind": "holiday", "group": "national_day"},
    ]
    r = await client.get(
        "/overview",
        params={"start": "2026-09-01", "end": "2026-09-02"},
        headers={"Accept-Language": "en"},
    )
    assert [h["name"] for h in r.json()["holidays"]] == [
        "National Day (day off in lieu)",
        "National Day",
    ]

    r = await client.get(
        f"/hotels/{ids['own']}", params={"start": STAY.isoformat(), "end": STAY.isoformat()}
    )
    assert r.status_code == 200
    types = sorted(e["event_type"] for e in r.json()["events"])
    assert types == ["price_up", "price_up", "rooms_decrease"]  # mức khách sạn + mức loại phòng
    assert r.json()["metrics"][0]["exact_rooms_left"] == 1

    r = await client.get(
        f"/hotels/{ids['own']}/dates/{STAY.isoformat()}", params={"history_days": 60}
    )
    assert r.status_code == 200
    d = r.json()
    assert len(d["room_types"]) == 1 and len(d["history"]) == 2 and len(d["latest"]) == 1
    assert d["latest"][0]["rooms_left"] == 1 and d["latest"][0]["stock_confidence"] == "exact"
    assert [o["status"] for o in d["observations"]] == ["available", "available"]
    assert d["compset"]["own_rank"] is None and d["compset"]["median_price"] is None
    assert d["compset"]["sample"] == "insufficient"
    assert d["holiday"] is None

    r = await client.get("/events", params={"event_type": "restock,rooms_decrease"})
    assert r.status_code == 200
    assert sorted(e["event_type"] for e in r.json()) == ["restock", "rooms_decrease"]
    assert all(e["hotel_name"] for e in r.json())
    r = await client.get("/events", params={"hotel_id": ids["other"]})
    assert r.status_code == 404
    r = await client.get(f"/hotels/{ids['other']}")
    assert r.status_code == 404
    r = await client.get("/runs")
    assert r.status_code == 200 and len(r.json()) == 2


async def test_day_detail_latest_and_coverage_ignore_history_window(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _snapshot_data(db, ids)
    await _login(client, "view@a.com", "view-pass-1")
    # Lâu không quét: cửa sổ 1 ngày không còn lượt nào, nhưng lần quét gần nhất vẫn hiện.
    url = f"/hotels/{ids['own']}/dates/{STAY.isoformat()}"
    d = (await client.get(url, params={"history_days": 1})).json()
    assert d["history"] == [] and d["observations"] == []
    assert d["latest_status"] == "available" and len(d["latest"]) == 1
    assert d["latest"][0]["rooms_left"] == 1 and len(d["room_types"]) == 1
    assert d["last_scan_at"].startswith("2026-09-24T14:00")
    assert d["last_scan_through"] == STAY.isoformat()

    # Đêm chưa từng được quét: không có dữ liệu nhưng đủ thông tin để giải thích vì sao.
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    horizon_end = (today + timedelta(days=29)).isoformat()
    far = STAY + timedelta(days=40)
    d = (await client.get(f"/hotels/{ids['own']}/dates/{far.isoformat()}")).json()
    assert d["latest_status"] is None and d["latest"] == [] and d["observations"] == []
    assert d["horizon_days"] == 30 and d["horizon_end"] == horizon_end
    assert d["last_scan_through"] == STAY.isoformat()
    assert (await client.get("/overview")).json()["horizon_end"] == horizon_end


async def test_day_detail_latest_reflects_sold_out_scan(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Lần quét mới nhất hết phòng: "lần quét gần nhất" không được hiện loại phòng còn của lần trước.
    ids = await _seed(db)
    await _snapshot_data(db, ids)
    await _login(client, "view@a.com", "view-pass-1")
    url = f"/hotels/{ids['own']}/dates/{STAY.isoformat()}"
    d = (await client.get(url, params={"history_days": 60})).json()
    assert d["latest_status"] == "available" and len(d["latest"]) == 1
    assert d["latest_scanned_at"] == d["latest"][0]["scanned_at"]

    run3 = scan_run("r3:booking", T0 + timedelta(hours=16), finished_at=T0 + timedelta(hours=17))
    run3.total_probes = 1
    db.add(run3)
    await db.flush()
    sold_out = ProbeResult(
        ProbeStatus.SOLD_OUT,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (),
        "<html/>",
        200,
        "s",
        10,
    )
    await SnapshotRepository(db, 10).write_probe(
        run3.id, ids["own"], "booking", STAY, sold_out, None, "1", "vn", T0 + timedelta(hours=16)
    )
    await db.commit()
    await AnalyticsService(db).run(run3.id)
    await db.commit()

    d = (await client.get(url, params={"history_days": 60})).json()
    assert d["latest_status"] == "sold_out" and d["latest"] == []
    assert d["latest_scanned_at"].startswith("2026-09-24T22:00")
    assert len(d["history"]) == 2  # lịch sử theo loại phòng vẫn giữ


async def test_last_run_and_runs_are_scoped_to_tenant(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Run chung toàn hệ thống: tenant chỉ thấy run có khách sạn của mình, số liệu chỉ của mình.
    ids = await _seed(db)
    await _snapshot_data(db, ids)  # 2 run chỉ gồm khách sạn của tenant A
    shared = scan_run(
        "r3:booking",
        T0 + timedelta(hours=16),
        status="partial",
        finished_at=T0 + timedelta(hours=17),
    )
    shared.total_jobs, shared.total_probes, shared.ok_count, shared.blocked_count = 2, 2, 1, 1
    db.add(shared)
    await db.flush()
    db.add_all(
        [
            ScanJob(
                scan_run_id=shared.id,
                hotel_id=ids["own"],
                start_date=STAY,
                horizon_days=1,
                status="done",
            ),
            ScanJob(
                scan_run_id=shared.id,
                hotel_id=ids["other"],
                start_date=STAY,
                horizon_days=1,
                status="failed",
            ),
        ]
    )
    repo = SnapshotRepository(db, 10)
    ok = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (_offer("1", 1, 1, "110"),),
        "<html/>",
        200,
        "s",
        10,
    )
    blocked = ProbeResult(
        ProbeStatus.BLOCKED,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        (),
        None,
        403,
        "s",
        10,
        error="blocked",
    )
    await repo.write_probe(
        shared.id, ids["own"], "booking", STAY, ok, None, "1", "vn", T0 + timedelta(hours=16)
    )
    await repo.write_probe(
        shared.id, ids["other"], "booking", STAY, blocked, None, "1", "vn", T0 + timedelta(hours=16)
    )
    await db.commit()
    shared_id = shared.id

    await _login(client, "op@x.com", "op-pass-123")
    a = (await client.get("/overview", params={"tenant_id": ids["t1"]})).json()["last_run"]
    assert a["id"] == shared_id and a["status"] == "completed"
    assert (a["total_jobs"], a["total_probes"], a["ok_count"], a["blocked_count"]) == (1, 1, 1, 0)
    # Lượt duy nhất của tenant B không thu được dữ liệu (bị chặn): không phải "cập nhật lúc…" (C2),
    # nhưng vẫn hiện trong danh sách lượt quét.
    b = (await client.get("/overview", params={"tenant_id": ids["t2"]})).json()["last_run"]
    assert b is None
    runs_b = (await client.get("/runs", params={"tenant_id": ids["t2"]})).json()
    assert [r["id"] for r in runs_b] == [shared_id]
    assert (runs_b[0]["status"], runs_b[0]["ok_count"], runs_b[0]["blocked_count"]) == (
        "partial",
        0,
        1,
    )
    runs_a = (await client.get("/runs", params={"tenant_id": ids["t1"]})).json()
    assert len(runs_a) == 3 and runs_a[0]["blocked_count"] == 0


async def test_new_tenant_has_no_last_run(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _snapshot_data(db, ids)
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get("/overview", params={"tenant_id": ids["t2"]})
    assert r.status_code == 200 and r.json()["last_run"] is None
    assert (await client.get("/runs", params={"tenant_id": ids["t2"]})).json() == []


async def test_insight_generate_enqueues_and_dedups(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/insights/generate")
    assert r.status_code == 202, r.text
    first = r.json()
    assert first["status"] == "pending" and first["trigger"] == "on_demand"
    assert queue.insights == [(ids["t1"], "on_demand", f"req{first['id']}")]
    r = await client.post("/insights/generate")
    assert r.json()["id"] == first["id"] and len(queue.insights) == 1
    r = await client.get("/insights")
    assert r.status_code == 200 and len(r.json()) == 1
    r = await client.get(f"/insights/{first['id']}")
    assert r.status_code == 200 and "input_json" in r.json()
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get(f"/insights/{first['id']}", params={"tenant_id": ids["t2"]})
    assert r.status_code == 404


async def test_health_endpoints_operator(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _snapshot_data(db, ids)
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get("/health/summary")
    assert r.status_code == 200
    assert (
        r.json()["last_run"]["status"] == "completed" and r.json()["pending_analytics_runs"] == []
    )
    r = await client.get("/health/runs")
    assert len(r.json()) == 2
    r = await client.get("/health/sessions")
    assert r.status_code == 200
    r = await client.get("/healthz")
    assert r.json() == {"status": "ok"}
    r = await client.get("/metrics")
    assert r.status_code == 200 and b"sb_probes_total" in r.content


async def test_pms_template_mapping_preview_import(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.get("/pms/template")
    assert r.status_code == 200 and r.text.startswith("stay_date,rooms_total")

    csv_bytes = (
        "Ngày,Tổng phòng,Phòng đã bán,ADR\n"
        "01/10/2026,120,96,1850000\n"
        "02/10/2026,120,130,1900000\n"
        "bad-date,120,10,1\n"
        "03/10/2026,120,60,\n"
    ).encode()
    r = await client.post("/pms/preview", files={"file": ("occ.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["suggested_mapping"] == {
        "stay_date": "Ngày",
        "rooms_total": "Tổng phòng",
        "rooms_sold": "Phòng đã bán",
        "adr": "ADR",
    }
    assert p["parsed_ok"] == 2 and [e["row"] for e in p["errors"]] == [2, 3]

    r = await client.put("/pms/mapping", json={"adapter": "csv", "mapping": p["suggested_mapping"]})
    assert r.status_code == 200
    r = await client.get("/pms/mapping")
    assert r.json()["mapping"]["stay_date"] == "Ngày"

    r = await client.post(
        "/pms/import",
        files={"file": ("occ.csv", csv_bytes, "text/csv")},
        data={"hotel_id": str(ids["comp"])},
    )
    assert r.status_code == 422  # chỉ khách sạn role=self
    r = await client.post(
        "/pms/import",
        files={"file": ("occ.csv", csv_bytes, "text/csv")},
        data={"hotel_id": str(ids["own"])},
    )
    assert r.status_code == 201, r.text
    imp = r.json()
    assert (imp["row_count"], imp["ok_count"], imp["status"]) == (4, 2, "partial")
    r = await client.get("/pms/daily")
    rows = r.json()
    assert len(rows) == 2
    row = next(x for x in rows if x["stay_date"] == "2026-10-01")
    assert row["rooms_available"] == 24 and row["occupancy_pct"] == "80.00"
    r = await client.get("/pms/imports")
    assert len(r.json()) == 1
    # import lại: upsert, không nhân đôi
    r = await client.post(
        "/pms/import",
        files={"file": ("occ.csv", csv_bytes, "text/csv")},
        data={"hotel_id": str(ids["own"])},
    )
    assert r.status_code == 201
    r = await client.get("/pms/daily")
    assert len(r.json()) == 2


async def test_overview_refundable_price_basis(client: AsyncClient, db: AsyncSession) -> None:
    """Giá hoàn huỷ: bạn bán gói không hoàn huỷ 90 và gói huỷ miễn phí 120; đối thủ chỉ có gói huỷ
    miễn phí 100. So mọi giá thì bạn rẻ hơn (90), so cùng điều kiện hoàn huỷ thì bạn đắt hơn (120)."""
    ids = await _seed(db)
    run = scan_run("rf:booking", T0, finished_at=T0 + timedelta(minutes=20))
    run.total_probes = 2
    db.add(run)
    await db.flush()
    repo = SnapshotRepository(db, 10)

    def probe(*rates: RatePlan) -> ProbeResult:
        offer = RoomOffer("1", "Room 1", 2, 3, 3, rates)
        return ProbeResult(
            ProbeStatus.OK,
            ProbeMethod.HTTP,
            STAY,
            STAY + timedelta(days=1),
            1,
            2,
            (offer,),
            "<html/>",
            200,
            "s",
            10,
        )

    own = probe(
        RatePlan("Non-refundable", Decimal("90"), "VND", False, None),
        RatePlan("Free cancellation", Decimal("120"), "VND", True, None),
    )
    comp = probe(RatePlan("Free cancellation", Decimal("100"), "VND", True, None))
    await repo.write_probe(run.id, ids["own"], "booking", STAY, own, None, "1", "vn", T0)
    await repo.write_probe(run.id, ids["comp"], "booking", STAY, comp, None, "1", "vn", T0)
    await db.commit()
    await AnalyticsService(db).run(run.id)
    await db.commit()
    await _login(client, "view@a.com", "view-pass-1")

    params = {"start": STAY.isoformat(), "end": STAY.isoformat()}
    any_ = (await client.get("/overview", params=params)).json()
    assert any_["hotels"][0]["cells"][0]["min_price"] == "90.00"
    assert any_["compset"][0]["own_min_price"] == "90.00"

    ref = (await client.get("/overview", params={**params, "price_basis": "refundable"})).json()
    assert ref["hotels"][0]["cells"][0]["min_price"] == "120.00"
    assert (
        ref["compset"][0]["own_min_price"] == "120.00"
        and ref["compset"][0]["min_price"] == "100.00"
    )
    # Cơ sở giá mới: có bữa sáng / chỉ phòng (gói không rõ bữa sáng không vào cơ sở nào).
    bf = (await client.get("/overview", params={**params, "price_basis": "breakfast"})).json()
    assert bf["hotels"][0]["cells"][0]["min_price"] is None

    bad = await client.get("/overview", params={**params, "price_basis": "cheapest"})
    assert bad.status_code == 422


async def test_export_overview_and_events_csv(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _snapshot_data(db, ids)
    await _login(client, "view@a.com", "view-pass-1")

    r = await client.get(
        "/export/overview.csv", params={"start": STAY.isoformat(), "end": STAY.isoformat()}
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "scrapebooking-tong-quan-2026-10-05.csv" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Kênh,Khách sạn,Vai trò,Đêm,Thứ,Trạng thái")
    lines = text.lstrip("﻿").strip().split("\r\n")
    assert len(lines) == 3  # tiêu đề + 2 khách sạn × 1 đêm
    assert lines[1].startswith(
        # 1 đối thủ: chưa đủ mẫu nên trung vị, chỉ số giá niêm yết, vị trí giá để trống.
        "Booking.com,Mine,Khách sạn của bạn,2026-10-05,T2,Còn phòng,1,110,VND,0,1,,,,2,"
    )

    r = await client.get("/export/events.csv", params={"event_type": "restock"})
    assert r.status_code == 200
    rows = r.content.decode("utf-8").lstrip("﻿").strip().split("\r\n")
    assert rows[0].startswith("Thời điểm quan sát,Kênh,Khách sạn")
    assert len(rows) == 2 and ",Có phòng lại," in rows[1]

    r = await client.get(
        "/export/events.csv", params={"event_type": "restock"}, headers={"Accept-Language": "en"}
    )
    assert "scrapebooking-events-" in r.headers["content-disposition"]
    rows = r.content.decode("utf-8").lstrip("﻿").strip().split("\r\n")
    assert rows[0].startswith("Observed at,Channel,Hotel") and ",Back in stock," in rows[1]

    assert (
        await client.get("/export/events.csv", params={"hotel_id": ids["other"]})
    ).status_code == 404


async def test_export_is_tenant_scoped(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _login(client, "view@a.com", "view-pass-1")
    r = await client.get("/export/overview.csv", params={"tenant_id": ids["t2"]})
    assert r.status_code == 403
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.get("/export/overview.csv", params={"tenant_id": ids["t2"]})
    body = r.content.decode("utf-8")
    assert r.status_code == 200 and "Mine" not in body and "Comp Hotel" not in body
    assert (await client.get("/export/events.csv")).status_code == 400  # operator phải chọn tenant
