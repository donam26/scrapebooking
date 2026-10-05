"""API đa kênh: thêm khách sạn/listing bằng URL bất kỳ kênh, xác nhận gợi ý, xem theo kênh."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.api.auth import hash_password
from app.channels import registry
from app.channels.registry import ChannelCode, ChannelInfo, ListingUrl, host_matches
from app.db.models import Listing, ListingDemandSignal, ScanRun, Tenant, TenantHotel, User
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.snapshots import SnapshotRepository
from tests.integration.conftest import FakeQueue
from tests.integration.seed import add_hotel, add_listing, scan_run

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
STAY = date(2026, 10, 5)
BOOKING_URL = "https://www.booking.com/hotel/vn/caravelle-saigon.html"
AGODA_URL = "https://www.agoda.com/caravelle-hotel/hotel/ho-chi-minh-city-vn.html"


def _agoda_url(url: str) -> ListingUrl | None:
    """Nhận diện URL Agoda tối giản (adapter thật do phần khác kiểm thử)."""
    if not host_matches(url, "agoda.com"):
        return None
    key = urlparse(url).path.strip("/").split("/")[0]
    return ListingUrl("agoda", key, f"https://www.agoda.com/{key}/hotel/x.html", "vn")


@pytest.fixture(autouse=True)
def two_channels(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Danh mục kênh cố định: Booking thật + Agoda tối giản, độc lập với adapter đang phát triển."""
    booking = registry.channels()[ChannelCode.BOOKING]
    agoda = ChannelInfo(ChannelCode.AGODA, "Agoda", "https://www.agoda.com/x", _agoda_url, True)
    monkeypatch.setattr(
        registry, "_CACHE", {ChannelCode.BOOKING: booking, ChannelCode.AGODA: agoda}
    )
    yield


async def _seed(db: AsyncSession) -> dict[str, int]:
    t1 = Tenant(name="A", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00"], horizon_days=30)
    t2 = Tenant(name="B", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00"], horizon_days=30)
    db.add_all([t1, t2])
    await db.flush()
    db.add_all(
        [
            User(
                tenant_id=t1.id,
                email="admin@a.com",
                password_hash=hash_password("admin-pass-1"),
                role="tenant_admin",
            ),
            User(
                tenant_id=t2.id,
                email="admin@b.com",
                password_hash=hash_password("admin-pass-2"),
                role="tenant_admin",
            ),
        ]
    )
    await db.commit()
    return {"t1": t1.id, "t2": t2.id}


async def _login(client: AsyncClient, email: str = "admin@a.com", pw: str = "admin-pass-1") -> None:
    r = await client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text


async def test_channels_endpoint(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    await _login(client)
    r = await client.get("/channels")
    assert r.status_code == 200
    assert [(c["code"], c["name"], c["collectable"], c["hosts"]) for c in r.json()] == [
        ("booking", "Booking.com", True, ["booking.com"]),
        ("agoda", "Agoda", True, ["agoda.com"]),
    ]


async def test_add_by_url_creates_unverified_listing_and_enqueues_verify(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client)
    r = await client.post("/watchlist", json={"url": BOOKING_URL + "?aid=1", "label": "CV"})
    assert r.status_code == 201, r.text
    hotel = r.json()["hotel"]
    [listing] = hotel["listings"]
    assert hotel["name"] is None and hotel["country_code"] == "vn"
    assert (listing["channel"], listing["listing_key"], listing["status"], listing["url"]) == (
        "booking",
        "vn/caravelle-saigon",
        "unverified",
        BOOKING_URL,
    )
    assert queue.verifies == [(listing["id"], "booking")]

    # URL kênh khác của trang không phải khách sạn: thông điệp cho người dùng.
    r = await client.post("/watchlist", json={"url": "https://www.example.com/hotel/x"})
    assert r.status_code == 422 and "Booking.com, Agoda" in r.json()["detail"]


async def test_same_listing_from_another_tenant_reuses_hotel(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client)
    first = (await client.post("/watchlist", json={"url": BOOKING_URL})).json()
    await _login(client, "admin@b.com", "admin-pass-2")
    r = await client.post(
        "/watchlist", json={"url": BOOKING_URL.replace(".html", ".vi.html"), "role": "self"}
    )
    assert r.status_code == 201
    assert r.json()["hotel"]["id"] == first["hotel"]["id"] and r.json()["role"] == "self"
    assert len(queue.verifies) == 1  # listing đã có: không kiểm tra lại
    assert len((await db.execute(select(Listing))).scalars().all()) == 1


async def test_pasting_a_suggested_url_confirms_it(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    hotel = await add_hotel(db, "vn/caravelle-saigon", name="Caravelle")
    suggestion = await add_listing(db, hotel.id, "agoda", "caravelle-hotel", status="suggested")
    db.add(TenantHotel(tenant_id=ids["t1"], hotel_id=hotel.id, role="competitor"))
    await db.commit()
    await _login(client)
    r = await client.post("/watchlist", json={"url": AGODA_URL})
    assert r.status_code == 201 and r.json()["hotel"]["id"] == hotel.id
    assert queue.verifies == [(suggestion.id, "agoda")]
    statuses = {lst["channel"]: lst["status"] for lst in r.json()["hotel"]["listings"]}
    assert statuses == {"booking": "active", "agoda": "unverified"}


async def test_add_listing_to_existing_hotel(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client)
    hotel_id = (await client.post("/watchlist", json={"url": BOOKING_URL})).json()["hotel"]["id"]
    queue.verifies.clear()
    r = await client.post(f"/watchlist/{hotel_id}/listings", json={"url": AGODA_URL})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["hotel_id"], body["channel"], body["listing_key"], body["status"]) == (
        hotel_id,
        "agoda",
        "caravelle-hotel",
        "unverified",
    )
    assert queue.verifies == [(body["id"], "agoda")]
    watch = (await client.get("/watchlist")).json()
    assert [lst["channel"] for lst in watch[0]["hotel"]["listings"]] == ["booking", "agoda"]

    # Dán URL khác cho kênh đã có: thay URL, kiểm tra lại.
    r = await client.post(
        f"/watchlist/{hotel_id}/listings",
        json={"url": "https://www.agoda.com/caravelle-saigon/hotel/x.html"},
    )
    assert r.status_code == 201 and r.json()["id"] == body["id"]
    assert r.json()["listing_key"] == "caravelle-saigon"
    # Khách sạn không thuộc watchlist của tenant: 404.
    assert (
        await client.post("/watchlist/999/listings", json={"url": AGODA_URL})
    ).status_code == 404


async def test_listing_of_another_hotel_is_409(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    await _login(client)
    a = (await client.post("/watchlist", json={"url": BOOKING_URL})).json()["hotel"]["id"]
    b_url = "https://www.booking.com/hotel/vn/rex.html"
    b = (await client.post("/watchlist", json={"url": b_url})).json()["hotel"]["id"]
    r = await client.post(f"/watchlist/{a}/listings", json={"url": AGODA_URL})
    assert r.status_code == 201
    r = await client.post(f"/watchlist/{b}/listings", json={"url": AGODA_URL})
    assert r.status_code == 409 and r.json()["detail"] == "url already linked to another hotel"
    r = await client.post(f"/watchlist/{b}/listings", json={"url": "https://x.example/h"})
    assert r.status_code == 422


async def test_confirm_reject_pause_resume_listing(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    hotel = await add_hotel(db, "vn/caravelle-saigon", name="Caravelle")
    db.add(TenantHotel(tenant_id=ids["t1"], hotel_id=hotel.id, role="competitor"))
    good = await add_listing(db, hotel.id, "agoda", "caravelle-hotel", status="suggested")
    good_id, hotel_id = good.id, hotel.id
    booking_id = (
        await db.execute(select(Listing.id).where(Listing.channel == "booking"))
    ).scalar_one()
    await db.commit()
    await _login(client)
    url = f"/watchlist/{hotel_id}/listings"

    r = await client.patch(f"{url}/{good_id}", json={"action": "confirm"})
    assert r.status_code == 200 and r.json()["status"] == "unverified"
    assert queue.verifies == [(good_id, "agoda")]
    # Đã xác nhận thì không còn là gợi ý.
    assert (await client.patch(f"{url}/{good_id}", json={"action": "confirm"})).status_code == 409
    assert (await client.patch(f"{url}/{good_id}", json={"action": "reject"})).status_code == 409

    r = await client.patch(f"{url}/{booking_id}", json={"action": "pause"})
    assert r.status_code == 200 and r.json()["status"] == "paused"
    r = await client.patch(f"{url}/{booking_id}", json={"action": "resume"})
    assert r.status_code == 200 and r.json()["status"] == "unverified"
    assert queue.verifies[-1] == (booking_id, "booking")
    assert (await client.patch(f"{url}/{booking_id}", json={"action": "nuke"})).status_code == 422
    assert (await client.patch(f"{url}/999", json={"action": "pause"})).status_code == 404

    # Gợi ý sai: bỏ (giữ dòng `rejected`), lần tìm sau không gợi ý lại.
    await db.execute(update(Listing).where(Listing.id == good_id).values(status="suggested"))
    await db.commit()
    r = await client.patch(f"{url}/{good_id}", json={"action": "reject"})
    assert r.status_code == 200 and r.json() is None
    # Gợi ý bị bỏ giữ dòng `rejected` (không gợi ý lại) và không hiện trong watchlist.
    rejected = (await db.execute(select(Listing.status).where(Listing.id == good_id))).scalar_one()
    assert rejected == "rejected"


async def test_discover_enqueues_channels_without_listing(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client)
    hotel_id = (await client.post("/watchlist", json={"url": BOOKING_URL})).json()["hotel"]["id"]
    r = await client.post(f"/watchlist/{hotel_id}/discover")
    assert r.status_code == 202 and r.json() == {"channels": ["agoda"]}
    assert queue.discovers == [(hotel_id, "agoda")]


# ---- xem theo kênh ----


def _ok(price: str, rooms: int) -> ProbeResult:
    offer = RoomOffer(
        "1", "Deluxe", 2, rooms, rooms, (RatePlan("Std", Decimal(price), "VND", True, None),)
    )
    return ProbeResult(
        ProbeStatus.OK, ProbeMethod.HTTP, STAY, STAY + timedelta(days=1), 1, 2, (offer,),
        "<html/>", 200, "s", 10,
    )  # fmt: skip


async def _two_channel_data(db: AsyncSession) -> dict[str, int]:
    ids = await _seed(db)
    own = await add_hotel(db, "vn/own", name="Own", channels=("booking", "agoda"))
    comp = await add_hotel(db, "vn/comp", name="Comp", channels=("booking", "agoda"))
    db.add_all(
        [
            TenantHotel(tenant_id=ids["t1"], hotel_id=own.id, role="self", label="Mine"),
            TenantHotel(tenant_id=ids["t1"], hotel_id=comp.id, role="competitor"),
        ]
    )
    repo = SnapshotRepository(db, 10)
    for channel, own_price, comp_price in (("booking", "100", "120"), ("agoda", "95", "130")):
        run = scan_run(f"r:{channel}", T0, channel=channel, finished_at=T0)
        db.add(run)
        await db.flush()
        await repo.write_probe(
            run.id, own.id, channel, STAY, _ok(own_price, 2), None, "1", "vn", T0
        )
        await repo.write_probe(
            run.id, comp.id, channel, STAY, _ok(comp_price, 4), None, "1", "vn", T0
        )
        run.total_probes = 2
        await db.commit()
        await AnalyticsService(db).run(run.id)
        await db.commit()
    db.add(
        ListingDemandSignal(
            hotel_id=own.id,
            channel="agoda",
            kind="bookings_24h",
            value=Decimal("13"),
            window_hours=24,
            raw_text="Đặt 13 lần trong 24 giờ qua",
            observed_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return {**ids, "own": own.id, "comp": comp.id}


async def test_overview_defaults_to_reference_channel_and_filters(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _two_channel_data(db)
    await _login(client)
    params = {"start": STAY.isoformat(), "end": STAY.isoformat()}
    body = (await client.get("/overview", params=params)).json()
    assert body["channel"] == "booking" and body["channels"] == ["booking", "agoda"]
    assert [h["cells"][0]["min_price"] for h in body["hotels"]] == ["100.00", "120.00"]
    assert body["compset"][0]["min_price"] == "120.00"

    body = (await client.get("/overview", params={**params, "channel": "agoda"})).json()
    assert body["channel"] == "agoda"
    assert [h["cells"][0]["min_price"] for h in body["hotels"]] == ["95.00", "130.00"]
    assert body["compset"][0]["min_price"] == "130.00"

    r = await client.get("/overview", params={**params, "channel": "nowhere"})
    assert r.status_code == 422

    # Đổi kênh tham chiếu của tenant: mặc định theo kênh đó.
    r = await client.patch("/settings", json={"reference_channel": "agoda"})
    assert r.status_code == 200 and r.json()["reference_channel"] == "agoda"
    assert (await client.get("/overview", params=params)).json()["channel"] == "agoda"
    r = await client.patch("/settings", json={"reference_channel": "expedia"})
    assert r.status_code == 422


async def test_hotel_and_day_detail_by_channel(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _two_channel_data(db)
    await _login(client)
    own = ids["own"]
    r = await client.get(
        f"/hotels/{own}", params={"start": STAY.isoformat(), "end": STAY.isoformat()}
    )
    assert r.json()["channel"] == "booking" and r.json()["metrics"][0]["min_price"] == "100.00"
    assert [(s["channel"], s["kind"], s["value"]) for s in r.json()["demand_signals"]] == [
        ("agoda", "bookings_24h", "13.000")
    ]
    r = await client.get(
        f"/hotels/{own}",
        params={"start": STAY.isoformat(), "end": STAY.isoformat(), "channel": "agoda"},
    )
    assert r.json()["metrics"][0]["min_price"] == "95.00"

    d = (await client.get(f"/hotels/{own}/dates/{STAY.isoformat()}")).json()
    assert d["channel"] == "booking"
    assert [(c["channel"], c["min_price"], c["exact_rooms_left"]) for c in d["channels"]] == [
        ("booking", "100.00", 2),
        ("agoda", "95.00", 2),
    ]
    assert d["latest"][0]["min_price"] == "100.00" and len(d["demand_signals"]) == 1
    d = (
        await client.get(f"/hotels/{own}/dates/{STAY.isoformat()}", params={"channel": "agoda"})
    ).json()
    assert d["channel"] == "agoda" and d["latest"][0]["min_price"] == "95.00"
    assert [rt["channel"] for rt in d["room_types"]] == ["agoda"]


async def test_day_channels_strip_flags_tax_basis_and_shows_label(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _two_channel_data(db)
    # Expedia chưa bảo đảm giá gồm thuế phí: hiện cạnh nhau nhưng đánh dấu không so được.
    run = scan_run("r:expedia", T0, channel="expedia", finished_at=T0)
    db.add(run)
    await db.flush()
    await SnapshotRepository(db, 10).write_probe(
        run.id, ids["own"], "expedia", STAY, _ok("80", 3), None, "1", "vn", T0
    )
    await db.commit()
    await AnalyticsService(db).run(run.id)
    await db.commit()
    await _login(client)
    d = (await client.get(f"/hotels/{ids['own']}/dates/{STAY.isoformat()}")).json()
    assert d["label"] == "Mine"
    assert [(c["channel"], c["min_price"], c["tax_inclusive"]) for c in d["channels"]] == [
        ("booking", "100.00", True),
        ("agoda", "95.00", True),
        ("expedia", "80.00", False),
    ]
    d = (await client.get(f"/hotels/{ids['comp']}/dates/{STAY.isoformat()}")).json()
    assert d["label"] is None and [c["channel"] for c in d["channels"]] == ["booking", "agoda"]


async def test_events_and_runs_carry_channel(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _two_channel_data(db)
    repo = SnapshotRepository(db, 10)
    later = T0 + timedelta(hours=8)
    run = scan_run("r2:agoda", later, channel="agoda", finished_at=later)
    db.add(run)
    await db.flush()
    await repo.write_probe(
        run.id, ids["comp"], "agoda", STAY, _ok("100", 1), None, "1", "vn", later
    )
    await db.commit()
    await AnalyticsService(db).run(run.id)
    await db.commit()
    await _login(client)

    events = (await client.get("/events")).json()
    assert events and {e["channel"] for e in events} == {"agoda"}
    assert (await client.get("/events", params={"channel": "booking"})).json() == []
    assert len((await client.get("/events", params={"channel": "agoda,booking"})).json()) == len(
        events
    )
    runs = (await client.get("/runs")).json()
    assert [r["channel"] for r in runs] == ["agoda", "agoda", "booking"]


async def test_scan_now_creates_one_run_per_channel(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    h1 = await add_hotel(db, "vn/h1", channels=("booking", "agoda"))
    h2 = await add_hotel(db, "vn/h2")
    await add_listing(db, h2.id, "agoda", "h2-agoda", status="suggested")  # chưa xác nhận
    db.add_all(
        [
            TenantHotel(tenant_id=ids["t1"], hotel_id=h1.id, role="self"),
            TenantHotel(tenant_id=ids["t1"], hotel_id=h2.id, role="competitor"),
        ]
    )
    await db.commit()
    await _login(client)
    r = await client.post("/watchlist/scan-now")
    assert r.status_code == 202, r.text
    runs = {run["channel"]: run for run in r.json()}
    assert set(runs) == {"booking", "agoda"}
    assert runs["agoda"]["trigger_key"].endswith(":agoda") and runs["agoda"]["total_jobs"] == 1
    assert runs["booking"]["total_jobs"] == 2
    assert sorted(zip(queue.probes, queue.probe_channels, strict=True)) == sorted(
        [
            ((runs["agoda"]["id"], h1.id), "agoda"),
            ((runs["booking"]["id"], h1.id), "booking"),
            ((runs["booking"]["id"], h2.id), "booking"),
        ]
    )
    # Gọi lại trong 10 phút: trả run đang chạy, không tạo thêm.
    again = await client.post("/watchlist/scan-now")
    assert sorted(x["id"] for x in again.json()) == sorted(x["id"] for x in r.json())
    assert len((await db.execute(select(ScanRun))).scalars().all()) == 2


async def test_scan_one_hotel_now_and_list_run_jobs(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    h1 = await add_hotel(db, "vn/h1", channels=("booking", "agoda"))
    h2 = await add_hotel(db, "vn/h2")
    other = await add_hotel(db, "vn/other")
    db.add_all(
        [
            TenantHotel(tenant_id=ids["t1"], hotel_id=h1.id, role="self", label="Của tôi"),
            TenantHotel(tenant_id=ids["t1"], hotel_id=h2.id, role="competitor"),
        ]
    )
    await db.commit()
    await _login(client)
    r = await client.post(f"/watchlist/{h2.id}/scan-now")
    assert r.status_code == 202, r.text
    [run] = r.json()
    assert run["channel"] == "booking" and run["total_jobs"] == 1
    assert ":h" in run["trigger_key"] and queue.probes == [(run["id"], h2.id)]
    # Khách sạn ngoài watchlist của tenant: 404.
    assert (await client.post(f"/watchlist/{other.id}/scan-now")).status_code == 404

    jobs = (await client.get(f"/runs/{run['id']}/jobs")).json()
    assert [j["hotel_id"] for j in jobs] == [h2.id]
    assert jobs[0]["status"] == "queued" and jobs[0]["total_probes"] == 0
    assert jobs[0]["error"] is None
    # Lượt quét cả watchlist: tên theo nhãn của tenant.
    full = (await client.post("/watchlist/scan-now")).json()
    booking = next(x for x in full if x["channel"] == "booking")
    names = {
        j["hotel_id"]: j["hotel_name"]
        for j in (await client.get(f"/runs/{booking['id']}/jobs")).json()
    }
    assert names[h1.id] == "Của tôi"
    assert (await client.get("/runs/999999/jobs")).status_code == 404


async def test_shared_listing_cannot_be_changed_by_one_of_several_tenants(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Review 01/10 (high #1): listing dùng chung — tenant B không được đổi URL / tạm dừng kênh của
    khách sạn mà tenant A cũng theo dõi; tenant đã gỡ khách sạn không được sửa listing."""
    ids = await _seed(db)
    await _login(client, "admin@b.com", "admin-pass-2")
    hotel_id = (await client.post("/watchlist", json={"url": BOOKING_URL})).json()["hotel"]["id"]
    db.add(TenantHotel(tenant_id=ids["t1"], hotel_id=hotel_id, role="self", active=True))
    await db.commit()
    listing_id = (
        await db.execute(select(Listing.id).where(Listing.hotel_id == hotel_id))
    ).scalar_one()
    await db.execute(update(Listing).where(Listing.id == listing_id).values(status="active"))
    await db.commit()

    url = f"/watchlist/{hotel_id}/listings"
    r = await client.patch(f"{url}/{listing_id}", json={"action": "pause"})
    assert r.status_code == 403
    other = "https://www.booking.com/hotel/vn/rex.html"
    assert (await client.post(url, json={"url": other})).status_code == 403
    # Dán lại đúng URL đang quét: không đặt lại trạng thái.
    r = await client.post(url, json={"url": BOOKING_URL})
    assert r.status_code == 201 and r.json()["status"] == "active"

    # Gỡ khách sạn khỏi watchlist: không còn quyền sửa listing.
    assert (await client.delete(f"/watchlist/{hotel_id}")).status_code == 204
    r = await client.patch(f"{url}/{listing_id}", json={"action": "retry"})
    assert r.status_code == 404
