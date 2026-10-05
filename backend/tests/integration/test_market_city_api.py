"""API thị trường toàn thành phố: khu vực (CRUD, tìm địa điểm, quét ngay), số liệu cả chợ một đêm,
bảng khách sạn; khách sạn thị trường không lọt vào tổng quan của tenant."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import hash_password
from app.api.main import create_app
from app.config import Settings
from app.db.models import Hotel, HotelDateMetric, ScanRun, Tenant, TenantHotel, User
from app.market.models import OccupancyEstimate
from app.marketscan.destinations import Destination, parse_destinations
from app.marketscan.models import MarketArea, MarketAreaHotel, MarketListPrice, MarketListScan
from app.scheduler.channel_pause import MemoryChannelPauses
from tests.fakes import FakeEmailSender
from tests.integration.conftest import FakeQueue
from tests.integration.seed import add_listing
from tests.integration.test_api import _login

NOW = datetime.now(tz=UTC)
TODAY = NOW.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
NIGHT = TODAY + timedelta(days=5)


class MarketQueue(FakeQueue):
    def __init__(self) -> None:
        super().__init__()
        self.market: list[int] = []
        self.rounds: list[tuple[str | None, int, int | None]] = []
        self.fail = False
        # API đọc tạm dừng kênh qua app.state.pauses (thay Redis trong test).
        self.pauses = MemoryChannelPauses(lambda: datetime.now(tz=UTC))

    async def enqueue_market_list(
        self,
        area_id: int,
        channel: str,
        start: str | None = None,
        index: int = 0,
        round_ts: int | None = None,
    ) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.market.append(area_id)
        self.rounds.append((start, index, round_ts))


class FakeSearch:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    async def __call__(self, query: str, country: str) -> list[Destination]:
        self.queries.append((query, country))
        path = (
            Path(__file__).parent.parent
            / "fixtures"
            / "html"
            / "autocomplete_ho_chi_minh_city.json"
        )
        return parse_destinations(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
async def mc(
    db: AsyncSession, settings: Settings
) -> AsyncIterator[tuple[AsyncClient, MarketQueue, FakeSearch]]:
    queue, search = MarketQueue(), FakeSearch()
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    app = create_app(settings=settings, session_factory=factory, queue=queue)
    app.state.email_sender = FakeEmailSender()
    app.state.destination_search = search
    app.state.pauses = queue.pauses
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, queue, search


def _tenant(name: str) -> Tenant:
    return Tenant(
        name=name,
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )


async def _seed(db: AsyncSession) -> dict[str, int]:
    a, b = _tenant("Rex"), _tenant("Other")
    own = Hotel(name="Rex Hotel", country_code="vn", lat=10.7769, lng=106.7009)
    comp = Hotel(name="Comp Watched", country_code="vn", review_count=50, review_score=Decimal("7"))
    m1 = Hotel(
        name="Alpha Hotel",
        country_code="vn",
        lat=10.7860,
        lng=106.7009,
        review_count=9000,
        review_score=Decimal("8.5"),
        star_rating=Decimal("4"),
        district="District 1",
        image_url="https://cf.bstatic.com/a.jpg",
    )
    m2 = Hotel(
        name="Beta Hotel",
        country_code="vn",
        lat=10.7769,
        lng=106.7209,
        review_count=100,
        review_score=Decimal("9.4"),
    )
    m3 = Hotel(name="Gamma Hotel", country_code="vn")
    m4 = Hotel(name="Delta Hotel", country_code="vn")
    db.add_all([a, b, own, comp, m1, m2, m3, m4])
    await db.flush()
    for h in (own, comp, m1, m2, m3, m4):
        await add_listing(db, h.id, "booking", f"vn/h{h.id}")
    db.add_all(
        [
            TenantHotel(tenant_id=a.id, hotel_id=own.id, role="self", active=True),
            TenantHotel(tenant_id=a.id, hotel_id=comp.id, role="competitor", active=True),
            User(
                tenant_id=a.id,
                email="admin@rex.vn",
                password_hash=hash_password("admin-pass-1"),
                role="tenant_admin",
                active=True,
            ),
            User(
                tenant_id=a.id,
                email="view@rex.vn",
                password_hash=hash_password("view-pass-1"),
                role="viewer",
                active=True,
            ),
            User(
                tenant_id=b.id,
                email="admin@other.vn",
                password_hash=hash_password("admin-pass-2"),
                role="tenant_admin",
                active=True,
            ),
        ]
    )
    await db.commit()
    return {
        "a": a.id,
        "b": b.id,
        "own": own.id,
        "comp": comp.id,
        "m1": m1.id,
        "m2": m2.id,
        "m3": m3.id,
        "m4": m4.id,
    }


async def test_area_crud_search_scan_now_and_permissions(
    mc: tuple[AsyncClient, MarketQueue, FakeSearch], db: AsyncSession
) -> None:
    client, queue, search = mc
    await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    assert (await client.get("/market/areas")).json() == []
    assert (
        await client.get("/market/areas/search", params={"q": "Ho Chi Minh"})
    ).status_code == 403
    body = {"name": "HCMC", "dest_id": "-3730078", "dest_type": "city"}
    assert (await client.post("/market/areas", json=body)).status_code == 403

    await _login(client, "admin@rex.vn", "admin-pass-1")
    r = await client.get("/market/areas/search", params={"q": "Ho Chi Minh"})
    assert r.status_code == 200, r.text
    assert [(d["dest_id"], d["dest_type"]) for d in r.json()] == [
        ("-3730078", "city"),
        ("2088", "district"),
        ("6750", "district"),
    ]
    assert r.json()[0]["nr_hotels"] == 6890 and search.queries == [("Ho Chi Minh", "vn")]

    r = await client.post("/market/areas", json=body)
    assert r.status_code == 201, r.text
    area = r.json()
    assert (area["list_nights"], area["detail_horizon_days"], area["detail_max_hotels"]) == (
        14,
        30,
        300,
    )
    assert (area["max_pages"], area["active"], area["channel"], area["hotels_total"]) == (
        60,
        True,
        "booking",
        0,
    )
    assert (await client.post("/market/areas", json=body)).status_code == 409
    bad = {**body, "dest_id": "2088", "dest_type": "district", "detail_horizon_days": 91}
    assert (await client.post("/market/areas", json=bad)).status_code == 422

    r = await client.patch(f"/market/areas/{area['id']}", json={"detail_max_hotels": 50})
    assert r.status_code == 200 and r.json()["detail_max_hotels"] == 50

    r = await client.post(f"/market/areas/{area['id']}/scan-now")
    assert r.status_code == 202 and r.json()["enqueued"] is True
    r = await client.post(f"/market/areas/{area['id']}/scan-now")
    assert r.json()["enqueued"] is False  # trong 10 phút: không đẩy thêm
    assert queue.market == [area["id"]]

    # Tenant khác không thấy, không sửa/xoá được khu vực này.
    await _login(client, "admin@other.vn", "admin-pass-2")
    assert (await client.get("/market/areas")).json() == []
    assert (
        await client.patch(f"/market/areas/{area['id']}", json={"name": "x"})
    ).status_code == 404
    assert (await client.delete(f"/market/areas/{area['id']}")).status_code == 404
    assert (await client.get("/market/city", params={"area_id": area["id"]})).status_code == 404

    await _login(client, "admin@rex.vn", "admin-pass-1")
    await client.patch(f"/market/areas/{area['id']}", json={"active": False})
    assert (await client.post(f"/market/areas/{area['id']}/scan-now")).status_code == 409
    assert (await client.delete(f"/market/areas/{area['id']}")).status_code == 204
    assert (await client.get("/market/areas")).json() == []


async def _seed_market(db: AsyncSession, ids: dict[str, int]) -> int:
    area = MarketArea(
        tenant_id=ids["a"],
        channel="booking",
        name="HCMC",
        dest_id="-3730078",
        dest_type="city",
        country_code="vn",
        list_nights=14,
        detail_horizon_days=30,
        detail_max_hotels=300,
        max_pages=60,
        active=True,
        last_list_scan_at=NOW - timedelta(hours=2),
    )
    db.add(area)
    await db.flush()
    for i, key in enumerate(("m1", "m2", "m3", "m4", "comp")):
        db.add(
            MarketAreaHotel(
                area_id=area.id,
                hotel_id=ids[key],
                first_seen_at=NOW - timedelta(days=3),
                last_seen_at=NOW - timedelta(hours=2),
                best_rank=i + 1,
            )
        )
    old = MarketListScan(
        area_id=area.id,
        stay_date=NIGHT,
        scanned_at=NOW - timedelta(days=1),
        properties_found=500,
        pages=1,
        hotels_seen=1,
        priced=1,
        status="completed",
    )
    scan = MarketListScan(
        area_id=area.id,
        stay_date=NIGHT,
        scanned_at=NOW - timedelta(hours=2),
        finished_at=NOW - timedelta(hours=1),
        properties_found=420,
        pages=1,
        hotels_seen=3,
        priced=3,
        status="completed",
    )
    db.add_all([old, scan])
    await db.flush()
    db.add(MarketListPrice(scan_id=old.id, hotel_id=ids["m3"], rank=1, price=Decimal("9e6")))
    for key, rank, price in (("m1", 1, "1200000"), ("m2", 2, "2500000"), ("comp", 3, "800000")):
        db.add(
            MarketListPrice(
                scan_id=scan.id, hotel_id=ids[key], rank=rank, price=Decimal(price), currency="VND"
            )
        )
    run = ScanRun(
        trigger_key="market:x",
        channel="booking",
        scheduled_at=NOW - timedelta(hours=1),
        started_at=NOW - timedelta(hours=1),
        status="completed",
    )
    db.add(run)
    await db.flush()
    for key, status_, left in (
        ("m2", "available", 4),
        ("m3", "sold_out", None),
        ("m4", "available", None),
        ("comp", "available", 2),
    ):
        db.add(
            HotelDateMetric(
                hotel_id=ids[key],
                channel="booking",
                stay_date=NIGHT,
                as_of_scan_run_id=run.id,
                days_to_arrival=5,
                availability_status=status_,
                exact_rooms_left=left,
                last_observed_at=NOW - timedelta(hours=1),
            )
        )
    # (khách sạn, lúc quét, tồn kho, còn thấp, còn cao, độ phủ): m4 khoảng quá rộng → không tin cậy.
    for key, ago, inv, lo, hi, cov in (
        ("m2", 1, 20, 4, 4, "1"),
        ("m3", 1, 10, 0, 0, "1"),
        ("m4", 1, 30, 10, 20, "1"),
        ("comp", 48, 10, 10, 10, "1"),
        ("comp", 1, 10, 2, 2, "1"),
    ):
        db.add(
            OccupancyEstimate(
                hotel_id=ids[key],
                channel="booking",
                stay_date=NIGHT,
                scan_run_id=run.id if ago == 1 else await _old_run(db, ids[key]),
                scanned_at=NOW - timedelta(hours=ago),
                days_to_arrival=5,
                status="sold_out" if lo == hi == 0 else "available",
                inventory=inv,
                left_low=lo,
                left_high=hi,
                occ_low=Decimal(inv - hi) / inv,
                occ_high=Decimal(inv - lo) / inv,
                coverage=Decimal(cov),
            )
        )
    await db.commit()
    return area.id


async def _old_run(db: AsyncSession, hotel_id: int) -> int:
    run = ScanRun(
        trigger_key=f"old:{hotel_id}",
        channel="booking",
        scheduled_at=NOW - timedelta(days=2),
        status="completed",
    )
    db.add(run)
    await db.flush()
    return run.id


async def test_city_summary_hotels_table_and_no_leak_into_overview(
    mc: tuple[AsyncClient, MarketQueue, FakeSearch], db: AsyncSession
) -> None:
    client, _, _ = mc
    ids = await _seed(db)
    await _login(client, "view@rex.vn", "view-pass-1")
    assert (await client.get("/market/city")).status_code == 404  # chưa có khu vực
    area_id = await _seed_market(db, ids)

    r = await client.get("/market/city", params={"date": NIGHT.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stay_date"] == NIGHT.isoformat() and body["channel"] == "booking"
    assert body["area"]["id"] == area_id and body["area"]["hotels_total"] == 5
    ls = body["list_scan"]
    assert (ls["status"], ls["properties_found"], ls["hotels_seen"], ls["priced"]) == (
        "completed",
        420,
        3,
        3,
    )
    # Thấy 3/420 khách sạn: giá là mẫu.
    assert ls["coverage"] == pytest.approx(3 / 420, abs=1e-4) and ls["sample"] is True
    prices = {k: Decimal(ls[k]) for k in ("avg", "median", "p25", "p75", "min", "max")}
    assert prices == {
        "avg": Decimal("1500000"),
        "median": Decimal("1200000"),
        "p25": Decimal("1000000"),
        "p75": Decimal("1850000"),
        "min": Decimal("800000"),
        "max": Decimal("2500000"),
    }
    hist = {(Decimal(b["lo"]), b["count"]) for b in ls["histogram"] if b["count"]}
    assert hist == {(Decimal(500000), 1), (Decimal(1000000), 1), (Decimal(2000000), 1)}
    assert len(ls["histogram"]) == 8 and ls["histogram"][-1]["hi"] is None
    d = body["detail"]
    assert (d["hotels_with_data"], d["hotels_available"], d["hotels_sold_out"]) == (4, 3, 1)
    # m2 còn 4/20, m3 hết 0/10, comp lần mới nhất 2/10; m4 không đủ tin cậy → 1 - 6/40.
    assert (d["rooms_left_known_sum"], d["inventory_sum"], d["coverage_hotels"]) == (6, 40, 3)
    assert Decimal(d["occupancy_est"]) == Decimal("0.85")

    # Mặc định đêm hôm nay: chưa có lượt quét danh sách nào.
    today = (await client.get("/market/city")).json()
    assert today["stay_date"] == TODAY.isoformat()
    assert today["list_scan"]["scan_id"] is None and today["list_scan"]["priced"] == 0
    assert today["list_scan"]["coverage"] is None and today["list_scan"]["sample"] is True

    url = "/market/city/hotels"
    r = await client.get(url, params={"date": NIGHT.isoformat()})
    assert r.status_code == 200, r.text
    rows = r.json()["items"]
    assert r.json()["total"] == 5
    assert [x["hotel_id"] for x in rows] == [ids[k] for k in ("m1", "m2", "comp", "m3", "m4")]
    alpha = rows[0]
    assert alpha["name"] == "Alpha Hotel" and alpha["url"].endswith(f"/vn/h{ids['m1']}.html")
    assert (alpha["review_count"], Decimal(alpha["review_score"]), Decimal(alpha["stars"])) == (
        9000,
        Decimal("8.5"),
        Decimal("4"),
    )
    assert (alpha["district"], alpha["image_url"]) == ("District 1", "https://cf.bstatic.com/a.jpg")
    assert alpha["distance_km"] == pytest.approx(1.01, abs=0.01)
    assert (Decimal(alpha["price"]), alpha["available"], alpha["rank"]) == (
        Decimal(1200000),
        True,
        1,
    )
    assert (alpha["watched"], alpha["role"]) == (False, None)
    by_id = {x["hotel_id"]: x for x in rows}
    assert (by_id[ids["comp"]]["watched"], by_id[ids["comp"]]["role"]) == (True, "competitor")
    assert by_id[ids["comp"]]["distance_km"] is None
    assert by_id[ids["m3"]]["available"] is False and by_id[ids["m3"]]["price"] is None
    assert by_id[ids["m4"]]["available"] is True  # quét chi tiết thấy còn phòng

    async def order(**params: str) -> list[int]:
        res = await client.get(url, params={"date": NIGHT.isoformat(), **params})
        return [x["hotel_id"] for x in res.json()["items"]]

    assert await order(sort="price") == [ids[k] for k in ("comp", "m1", "m2", "m3", "m4")]
    assert (await order(sort="distance"))[:2] == [ids["m1"], ids["m2"]]
    assert (await order(sort="review_score"))[:3] == [ids["m2"], ids["m1"], ids["comp"]]
    assert await order(q="alp") == [ids["m1"]]
    assert await order(limit="2", offset="1") == [ids["m2"], ids["comp"]]
    assert (await client.get(url, params={"sort": "bogus"})).status_code == 422

    # Vắng mặt trên danh sách chỉ là "hết phòng" khi danh sách phủ ≥ 98% số kênh báo.
    await db.execute(delete(HotelDateMetric).where(HotelDateMetric.hotel_id == ids["m4"]))
    await db.commit()

    async def m4_available() -> bool | None:
        res = await client.get(url, params={"date": NIGHT.isoformat(), "q": "Delta"})
        return res.json()["items"][0]["available"]  # type: ignore[no-any-return]

    assert await m4_available() is None  # danh sách là mẫu 3/420: chưa biết
    await db.execute(
        update(MarketListScan).where(MarketListScan.hotels_seen == 3).values(properties_found=3)
    )
    await db.commit()
    assert await m4_available() is False
    full = (await client.get("/market/city", params={"date": NIGHT.isoformat()})).json()
    assert (full["list_scan"]["coverage"], full["list_scan"]["sample"]) == (1.0, False)
    # Lượt mới hơn còn đang chạy (mới vài thẻ): vẫn hiện lượt "completed" mới nhất của đêm.
    db.add(
        MarketListScan(
            area_id=area_id,
            stay_date=NIGHT,
            scanned_at=NOW,
            properties_found=400,
            hotels_seen=2,
            status="running",
        )
    )
    await db.commit()
    again = (await client.get("/market/city", params={"date": NIGHT.isoformat()})).json()
    assert again["list_scan"]["scan_id"] == full["list_scan"]["scan_id"]

    # Khách sạn thị trường không lọt vào tổng quan/compset của tenant.
    r = await client.get("/overview", params={"start": NIGHT.isoformat(), "end": NIGHT.isoformat()})
    assert r.status_code == 200, r.text
    assert {h["hotel"]["id"] for h in r.json()["hotels"]} == {ids["own"], ids["comp"]}


async def test_scan_now_guards_and_load_ceilings(
    mc: tuple[AsyncClient, MarketQueue, FakeSearch], db: AsyncSession
) -> None:
    client, queue, _ = mc
    await _seed(db)
    await _login(client, "admin@rex.vn", "admin-pass-1")
    body = {"name": "HCMC", "dest_id": "-3730078", "dest_type": "city"}
    # Kẹp cấu hình theo trần hệ thống; list_nights tối đa 30.
    r = await client.post(
        "/market/areas", json={**body, "detail_max_hotels": 5000, "max_pages": 100}
    )
    assert r.status_code == 201, r.text
    area = r.json()
    assert (area["detail_max_hotels"], area["max_pages"]) == (500, 100)
    r = await client.patch(f"/market/areas/{area['id']}", json={"detail_max_hotels": 900})
    assert r.json()["detail_max_hotels"] == 500
    bad = {**body, "dest_id": "1", "list_nights": 31}
    assert (await client.post("/market/areas", json=bad)).status_code == 422
    for dest in ("2088", "6750"):
        r = await client.post(
            "/market/areas", json={**body, "dest_id": dest, "dest_type": "district"}
        )
        assert r.status_code == 201
    r = await client.post("/market/areas", json={**body, "dest_id": "9", "dest_type": "district"})
    assert r.status_code == 409 and r.json()["detail"] == "at most 3 market areas per tenant"

    url = f"/market/areas/{area['id']}/scan-now"
    # Redis lỗi khi đẩy job: 503 và yêu cầu được trả lại (lần sau còn quét được).
    queue.fail = True
    assert (await client.post(url)).status_code == 503
    row = await db.get(MarketArea, area["id"])
    assert row is not None
    await db.refresh(row)
    assert row.list_requested_at is None and row.last_list_status is None
    queue.fail = False
    r = await client.post(url)
    assert r.status_code == 202 and r.json()["enqueued"] is True
    await db.refresh(row)
    assert row.last_list_status == "queued" and row.list_requested_at is not None
    assert queue.rounds == [(TODAY.isoformat(), 0, int(row.list_requested_at.timestamp()))]

    # Vòng đang chạy (tiến triển ≤ 30 phút trước): không mở vòng mới dù đã quá 10 phút.
    now = datetime.now(tz=UTC)
    row.list_requested_at = now - timedelta(hours=1)
    row.last_list_status, row.last_list_scan_at = "running", now - timedelta(minutes=5)
    await db.commit()
    assert (await client.post(url)).json()["enqueued"] is False
    row.last_list_scan_at = now - timedelta(minutes=40)  # chuỗi đứng yên: cho mở vòng mới
    await db.commit()
    assert (await client.post(url)).json()["enqueued"] is True
    assert len(queue.market) == 2

    # Trang danh sách vừa bị chặn: từ chối "Quét ngay" tới khi hết tạm dừng.
    row.list_requested_at = now - timedelta(hours=1)
    row.last_list_status = "blocked"
    await db.commit()
    await queue.pauses.pause("booking:market", 30, "blocked")
    r = await client.post(url)
    assert r.status_code == 409 and r.json()["detail"].startswith("channel paused")
    assert len(queue.market) == 2


async def test_destination_search_is_throttled_per_tenant(
    mc: tuple[AsyncClient, MarketQueue, FakeSearch], db: AsyncSession
) -> None:
    client, _, search = mc
    await _seed(db)
    await _login(client, "admin@rex.vn", "admin-pass-1")
    for _ in range(10):
        r = await client.get("/market/areas/search", params={"q": "Saigon"})
        assert r.status_code == 200
    r = await client.get("/market/areas/search", params={"q": "Saigon"})
    assert r.status_code == 429 and len(search.queries) == 10
    # Tenant khác có hạn mức riêng.
    await _login(client, "admin@other.vn", "admin-pass-2")
    assert (await client.get("/market/areas/search", params={"q": "Hanoi"})).status_code == 200
