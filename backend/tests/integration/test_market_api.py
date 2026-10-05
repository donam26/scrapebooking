"""API nhịp đặt phòng + gợi ý giá, dữ liệu chèn thẳng qua ORM (không phụ thuộc collector/analytics)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import hash_password
from app.config import Settings
from app.db.models import (
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    Probe,
    RoomSnapshot,
    RoomType,
    ScanJob,
    ScanRun,
    Tenant,
    TenantHotel,
    User,
)
from app.market.jobs import estimate_occupancy_catch_up
from app.market.models import OccupancyEstimate, OccupancyEstimateRun
from app.market.occupancy_service import RETRY_AFTER, OccupancyService, reset_occupancy_marker
from app.market.weather import Weather, WeatherDay, WeatherNow
from tests.integration.test_api import _login

NOW = datetime.now(tz=UTC)
TODAY = NOW.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
NIGHT = TODAY + timedelta(days=5)


async def _seed(db: AsyncSession) -> dict[str, int]:
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
    own = Hotel(name="Rex Hotel", country_code="vn")
    a = Hotel(name="Comp A", country_code="vn")
    b = Hotel(name="Comp B", country_code="vn")
    db.add_all([t, own, a, b])
    await db.flush()
    db.add_all(
        [
            TenantHotel(tenant_id=t.id, hotel_id=own.id, role="self", active=True, label="Rex"),
            TenantHotel(tenant_id=t.id, hotel_id=a.id, role="competitor", active=True),
            TenantHotel(tenant_id=t.id, hotel_id=b.id, role="competitor", active=True),
            User(
                tenant_id=t.id,
                email="admin@rex.vn",
                password_hash=hash_password("admin-pass-1"),
                role="tenant_admin",
                active=True,
            ),
            User(
                tenant_id=t.id,
                email="view@rex.vn",
                password_hash=hash_password("view-pass-1"),
                role="viewer",
                active=True,
            ),
        ]
    )
    rts = {}
    for h in (own, a, b):
        rt = RoomType(
            hotel_id=h.id,
            channel="booking",
            external_room_id="1",
            name="Deluxe",
            first_seen_at=NOW - timedelta(days=10),
            last_seen_at=NOW,
        )
        db.add(rt)
        await db.flush()
        rts[h.id] = rt.id
    await db.commit()
    return {"t": t.id, "own": own.id, "a": a.id, "b": b.id, **{f"rt{k}": v for k, v in rts.items()}}


async def _observe(
    db: AsyncSession,
    ids: dict[str, int],
    key: str,
    at: datetime,
    states: dict[int, tuple[str, int | None]],
) -> int:
    """Một lượt quét đêm NIGHT: mỗi khách sạn (trạng thái, số phòng còn chính xác)."""
    run = ScanRun(
        trigger_key=key,
        channel="booking",
        scheduled_at=at,
        started_at=at,
        finished_at=at + timedelta(minutes=5),
        status="completed",
        total_probes=len(states),
    )
    db.add(run)
    await db.flush()
    for hotel_id, (status, left) in states.items():
        probe = Probe(
            scan_run_id=run.id,
            hotel_id=hotel_id,
            channel="booking",
            stay_date=NIGHT,
            checkin=NIGHT,
            checkout=NIGHT + timedelta(days=1),
            nights=1,
            adults=2,
            status="ok" if status == "available" else "sold_out",
            fetched_at=at,
        )
        db.add(probe)
        await db.flush()
        if status == "available":
            db.add(
                RoomSnapshot(
                    probe_id=probe.id,
                    hotel_id=hotel_id,
                    channel="booking",
                    room_type_id=ids[f"rt{hotel_id}"],
                    stay_date=NIGHT,
                    scanned_at=at,
                    rooms_left=left,
                    stock_confidence="exact",
                )
            )
        db.add(
            HotelDateSnapshot(
                hotel_id=hotel_id,
                stay_date=NIGHT,
                scan_run_id=run.id,
                channel="booking",
                scanned_at=at,
                status=status,
                exact_rooms_left=left,
            )
        )
    await db.commit()
    return run.id


async def test_pace_estimates_suggestion_and_decision_flow(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    own, a, b = ids["own"], ids["a"], ids["b"]
    r0 = await _observe(
        db,
        ids,
        "r0",
        NOW - timedelta(days=3),
        {own: ("available", 8), a: ("available", 10), b: ("available", 10)},
    )
    r1 = await _observe(
        db,
        ids,
        "r1",
        NOW - timedelta(hours=1),
        {own: ("available", 6), a: ("sold_out", None), b: ("available", 1)},
    )
    for hotel_id, status, price, left in (
        (own, "available", Decimal("80"), 6),
        (a, "sold_out", None, None),
        (b, "available", Decimal("100"), 1),
    ):
        db.add(
            HotelDateMetric(
                hotel_id=hotel_id,
                channel="booking",
                stay_date=NIGHT,
                as_of_scan_run_id=r1,
                days_to_arrival=5,
                min_price=price,
                currency="VND",
                availability_status=status,
                exact_rooms_left=left,
                last_observed_at=NOW - timedelta(hours=1),
            )
        )
    await db.commit()

    svc = OccupancyService(db)
    assert set(await svc.pending_run_ids()) == {r0, r1}
    assert await svc.run(r0) == 3 and await svc.run(r1) == 3
    await db.commit()
    assert await svc.pending_run_ids() == []

    await _login(client, "view@rex.vn", "view-pass-1")
    params = {"start": NIGHT.isoformat(), "end": NIGHT.isoformat()}
    r = await client.get("/market/pace", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channel"] == "booking" and body["own_hotel_id"] == own
    n = body["nights"][0]
    # Bạn: 6/8 còn → 25%; đối thủ A hết (100%), B còn 1/10 (90%) → trung vị 95%
    assert n["own_occ"]["occ_mid"] == "0.2500" and n["own_occ"]["reliable"] is True
    assert n["comp_occ"] == "0.9500" and n["comp_occ_hotels"] == 2
    assert n["comp_sold_out"] == 1 and n["comp_observed"] == 2
    sug = n["suggestion"]
    assert sug["kind"] == "raise" and sug["change_pct"] == 15 and sug["decision"] is None
    assert sug["hotel_id"] == own and sug["price_basis"] == "any" and n["suggestions"] == [sug]
    assert "1/2 đối thủ đã hết phòng" in sug["reasons"]
    en = (await client.get("/market/pace", params=params, headers={"Accept-Language": "en"})).json()
    assert "1/2 competitors sold out" in en["nights"][0]["suggestion"]["reasons"]

    path = f"/market/suggestions/{NIGHT.isoformat()}/raise"
    assert (await client.put(path, json={"decision": "applied"})).status_code == 403
    await _login(client, "admin@rex.vn", "admin-pass-1")
    put = await client.put(path, json={"decision": "applied"}, headers={"Accept-Language": "en"})
    assert put.status_code == 200 and "1/2 competitors sold out" in put.json()["reasons"]
    again = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert again["suggestion"]["decision"] == "applied"
    wrong = f"/market/suggestions/{NIGHT.isoformat()}/lower"
    assert (await client.put(wrong, json={"decision": "applied"})).status_code == 409
    assert (await client.delete(path)).status_code == 204
    undone = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert undone["suggestion"]["decision"] is None

    too_long = {"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=60)).isoformat()}
    assert (await client.get("/market/pace", params=too_long)).status_code == 422


async def test_pace_empty_tenant_returns_nights_without_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    body = (await client.get("/market/pace")).json()
    assert len(body["nights"]) == 30 and body["data_since"] is None
    assert all(n["own_occ"] is None and n["suggestion"] is None for n in body["nights"])
    assert body["calibration"]["nights"] == 0 and ids["own"] == body["own_hotel_id"]
    assert date.fromisoformat(body["start"]) == TODAY


async def test_holidays_default_twelve_months_and_range_guard(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    body = (await client.get("/market/holidays", params={"start": "2026-04-01"})).json()
    names = {h["name"] for h in body}
    assert "Ngày Giải phóng miền Nam" in names and "Tết Dương lịch" in names
    en = await client.get(
        "/market/holidays", params={"start": "2026-04-01"}, headers={"Accept-Language": "en"}
    )
    assert "Reunification Day" in {h["name"] for h in en.json()}
    assert all("2026-04-01" <= h["date"] <= "2027-04-01" for h in body)
    bad = {"start": "2026-01-01", "end": "2027-12-31"}
    assert (await client.get("/market/holidays", params=bad)).status_code == 422


async def test_weather_not_configured_then_uses_own_hotel_coordinates(
    client: AsyncClient, db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    assert (await client.get("/market/weather")).json()["configured"] is False

    settings.openweather_api_key = "test-key"
    body = (await client.get("/market/weather")).json()
    assert body["configured"] is True and body["error"]

    own = await db.get(Hotel, ids["own"])
    comp = await db.get(Hotel, ids["a"])
    assert own is not None and comp is not None
    own.lat, own.lng = 10.7757, 106.7014
    comp.lat, comp.lng = 21.0, 105.8
    await db.commit()
    seen: list[tuple[float, float]] = []

    async def fake_fetch(lat: float, lng: float, api_key: str, lang: str = "vi") -> Weather:
        seen.append((lat, lng))
        return Weather(
            location="Ho Chi Minh City",
            current=WeatherNow(
                temp=30.0, feels_like=34.0, humidity=70, description="mây", icon="03d"
            ),
            days=[WeatherDay(TODAY, 25.0, 32.0, "mưa nhẹ", "10d", 0.6)],
        )

    monkeypatch.setattr("app.api.routers.market.fetch_weather", fake_fetch)
    body = (await client.get("/market/weather")).json()
    assert seen == [(10.7757, 106.7014)]
    assert body["location"] == "Ho Chi Minh City" and body["current"]["temp"] == 30.0
    assert body["days"][0]["pop"] == 0.6 and body["error"] is None


async def test_occupancy_per_hotel_lists_watchlist_hotels(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    body = (await client.get("/market/occupancy")).json()
    assert body["channel"] == "booking"
    assert [h["hotel_id"] for h in body["hotels"]][0] == ids["own"]
    assert {h["role"] for h in body["hotels"]} == {"self", "competitor"}
    assert all(h["nights"] == [] for h in body["hotels"])
    bad = {"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=60)).isoformat()}
    assert (await client.get("/market/occupancy", params=bad)).status_code == 422


async def test_local_events_crud_and_permissions(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    body = {
        "name": "F1 Grand Prix",
        "category": "sports",
        "start_date": (TODAY + timedelta(days=10)).isoformat(),
        "end_date": (TODAY + timedelta(days=12)).isoformat(),
        "expected_uplift_pct": 40,
    }
    assert (await client.post("/market/events", json=body)).status_code == 403
    await _login(client, "admin@rex.vn", "admin-pass-1")
    created = (await client.post("/market/events", json=body)).json()
    assert created["id"] and created["expected_uplift_pct"] == 40
    listed = (await client.get("/market/events")).json()
    assert [e["name"] for e in listed] == ["F1 Grand Prix"]
    upd = {**body, "name": "F1 Vietnam", "category": "festival", "expected_uplift_pct": None}
    r = await client.put(f"/market/events/{created['id']}", json=upd)
    assert r.status_code == 200 and r.json()["name"] == "F1 Vietnam"
    inverted = {**body, "start_date": body["end_date"], "end_date": body["start_date"]}
    assert (await client.post("/market/events", json=inverted)).status_code == 422
    assert (await client.post("/market/events", json={**body, "category": "x"})).status_code == 422
    assert (await client.delete(f"/market/events/{created['id']}")).status_code == 204
    assert (await client.get("/market/events")).json() == []
    assert (await client.delete(f"/market/events/{created['id']}")).status_code == 404


async def test_market_runs_are_not_the_tenants_last_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Run thị trường cả khu vực chạm khách sạn của tenant nhưng không phải "lượt quét gần nhất"."""
    ids = await _seed(db)
    run = ScanRun(
        trigger_key="market:99:20261002",
        channel="booking",
        scheduled_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        status="completed",
    )
    db.add(run)
    await db.flush()
    db.add(
        ScanJob(
            scan_run_id=run.id, hotel_id=ids["own"], start_date=TODAY, horizon_days=1, status="done"
        )
    )
    await db.commit()
    await _login(client, "view@rex.vn", "view-pass-1")
    body = (
        await client.get("/overview", params={"start": TODAY.isoformat(), "end": TODAY.isoformat()})
    ).json()
    assert body["last_run"] is None
    # Danh sách lượt quét vẫn có run đó nhưng che mã khu vực của tenant khác.
    runs = (await client.get("/runs")).json()
    assert [r["trigger_key"] for r in runs] == ["market"]


def _metric(
    hotel_id: int,
    status: str,
    price: Decimal | None,
    left: int | None,
    run_id: int,
    *,
    refundable: Decimal | None = None,
    currency: str | None = "VND",
) -> HotelDateMetric:
    return HotelDateMetric(
        hotel_id=hotel_id,
        channel="booking",
        stay_date=NIGHT,
        as_of_scan_run_id=run_id,
        days_to_arrival=5,
        min_price=price,
        min_refundable_price=refundable,
        currency=currency,
        availability_status=status,
        exact_rooms_left=left,
        last_observed_at=NOW - timedelta(hours=1),
    )


async def _add_hotel(db: AsyncSession, tenant_id: int, name: str, role: str) -> int:
    h = Hotel(name=name, country_code="vn")
    db.add(h)
    await db.flush()
    db.add(TenantHotel(tenant_id=tenant_id, hotel_id=h.id, role=role, active=True, label=name))
    await db.commit()
    return h.id


async def test_two_self_hotels_get_their_own_suggestions_and_decisions(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    own, a, b = ids["own"], ids["a"], ids["b"]
    own2 = await _add_hotel(db, ids["t"], "Rex Annex", "self")
    assert own2 > own  # khách sạn chính = id nhỏ nhất
    run = await _observe(
        db, ids, "r1", NOW - timedelta(hours=1), {a: ("sold_out", None), b: ("available", 1)}
    )
    db.add_all(
        [
            _metric(own, "available", Decimal("80"), 6, run),
            _metric(own2, "available", Decimal("90"), 2, run),
            _metric(a, "sold_out", None, None, run, currency=None),
            _metric(b, "available", Decimal("100"), 1, run),
        ]
    )
    await db.commit()
    await _login(client, "admin@rex.vn", "admin-pass-1")
    params = {"start": NIGHT.isoformat(), "end": NIGHT.isoformat()}
    body = (await client.get("/market/pace", params=params)).json()
    assert body["own_hotel_id"] == own
    n = body["nights"][0]
    assert n["suggestion"]["hotel_id"] == own and n["own_price"] == "80.00"
    # Mỗi khách sạn self một gợi ý riêng (giá riêng → mức tăng riêng), theo thứ tự hotel_id.
    assert [(s["hotel_id"], s["kind"], s["change_pct"]) for s in n["suggestions"]] == [
        (own, "raise", 15),
        (own2, "raise", 10),
    ]

    path = f"/market/suggestions/{NIGHT.isoformat()}/raise"
    comp = await client.put(path, json={"decision": "applied"}, params={"hotel_id": a})
    assert comp.status_code == 404  # đối thủ không phải khách sạn self
    put = await client.put(path, json={"decision": "dismissed"}, params={"hotel_id": own2})
    assert put.status_code == 200
    assert put.json()["hotel_id"] == own2 and put.json()["decision"] == "dismissed"
    n = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert n["suggestion"]["decision"] is None  # khách sạn chính chưa ghi nhận
    assert [s["decision"] for s in n["suggestions"]] == [None, "dismissed"]
    # Không có hotel_id: khách sạn chính.
    assert (await client.put(path, json={"decision": "applied"})).status_code == 200
    n = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert n["suggestion"]["decision"] == "applied"
    assert [s["decision"] for s in n["suggestions"]] == ["applied", "dismissed"]
    assert (await client.delete(path, params={"hotel_id": b})).status_code == 404
    assert (await client.delete(path, params={"hotel_id": own2})).status_code == 204
    n = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert [s["decision"] for s in n["suggestions"]] == ["applied", None]


async def test_suggestion_uses_refundable_basis_and_skips_other_currency(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    own, a, b = ids["own"], ids["a"], ids["b"]
    c = await _add_hotel(db, ids["t"], "Comp C", "competitor")
    run = await _observe(db, ids, "r1", NOW - timedelta(hours=1), {a: ("sold_out", None)})
    db.add_all(
        [
            _metric(own, "available", Decimal("80"), 6, run, refundable=Decimal("88")),
            _metric(a, "sold_out", None, None, run, currency=None),
            _metric(b, "available", Decimal("100"), 3, run, refundable=Decimal("110")),
            _metric(c, "available", Decimal("4"), 3, run, refundable=Decimal("5"), currency="USD"),
        ]
    )
    await db.commit()
    await _login(client, "view@rex.vn", "view-pass-1")
    params = {"start": NIGHT.isoformat(), "end": NIGHT.isoformat()}
    n = (await client.get("/market/pace", params=params)).json()["nights"][0]
    # C (USD) bị bỏ, A hết phòng (không có giá) vẫn đếm; so giá hoàn huỷ 88 với 110.
    assert n["comp_observed"] == 2 and n["comp_sold_out"] == 1 and n["currency"] == "VND"
    assert n["own_price"] == "88.00" and n["comp_median_price"] == "110.00"
    sug = n["suggestion"]
    assert sug["price_basis"] == "refundable" and sug["kind"] == "raise" and sug["change_pct"] == 15
    assert "giá bạn thấp hơn trung vị đối thủ 20%" in sug["reasons"]

    # Bạn không còn giá hoàn huỷ → so giá thấp nhất mọi loại.
    m = (
        await db.execute(select(HotelDateMetric).where(HotelDateMetric.hotel_id == own))
    ).scalar_one()
    m.min_refundable_price = None
    await db.commit()
    n = (await client.get("/market/pace", params=params)).json()["nights"][0]
    assert n["suggestion"]["price_basis"] == "any"
    assert n["own_price"] == "80.00" and n["comp_median_price"] == "100.00"


async def test_occupancy_days_to_arrival_uses_hotel_local_date(db: AsyncSession) -> None:
    ids = await _seed(db)
    own = ids["own"]
    day = TODAY - timedelta(days=2)
    # 06:00 giờ Việt Nam = 23:00 UTC hôm trước; 14:00 cùng ngày địa phương = 07:00 UTC.
    dawn = datetime.combine(day - timedelta(days=1), time(23, 0), tzinfo=UTC)
    noon = datetime.combine(day, time(7, 0), tzinfo=UTC)
    r_dawn = await _observe(db, ids, "dawn", dawn, {own: ("available", 6)})
    r_noon = await _observe(db, ids, "noon", noon, {own: ("available", 5)})
    svc = OccupancyService(db)
    assert await svc.run(r_dawn) == 1 and await svc.run(r_noon) == 1
    await db.commit()
    rows = await db.execute(
        select(OccupancyEstimate.scan_run_id, OccupancyEstimate.days_to_arrival).where(
            OccupancyEstimate.hotel_id == own
        )
    )
    expected = (NIGHT - day).days
    assert dict(rows.all()) == {r_dawn: expected, r_noon: expected}  # type: ignore[arg-type]


async def test_failed_occupancy_run_is_retried_with_backoff_then_parked(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _seed(db)
    run = await _observe(db, ids, "r1", NOW - timedelta(hours=1), {ids["own"]: ("available", 6)})

    async def boom(self: OccupancyService, run_id: int) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(OccupancyService, "run", boom)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    assert await estimate_occupancy_catch_up({"session_factory": factory}) == 0
    marker = select(OccupancyEstimateRun.rows).where(OccupancyEstimateRun.scan_run_id == run)
    assert (await db.execute(marker)).scalar_one() == -1  # lần thử 1, không phải dấu vĩnh viễn
    svc = OccupancyService(db)
    assert await svc.pending_run_ids() == []  # chưa tới hạn thử lại
    later = NOW + RETRY_AFTER + timedelta(hours=1)
    assert await svc.pending_run_ids(now=later) == [run]
    assert await svc.mark_failed(run) == 2 and await svc.mark_failed(run) == 3
    await db.commit()
    assert (await db.execute(marker)).scalar_one() == -3
    assert await svc.pending_run_ids(now=later + timedelta(days=2)) == []  # đủ 3 lần: để nguyên
    assert await reset_occupancy_marker(db, run) is True
    await db.commit()
    assert await svc.pending_run_ids() == [run]
    assert await reset_occupancy_marker(db, run) is False
