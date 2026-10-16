import asyncio
import os

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.db.models import Hotel, Listing, ScanRun, Tenant, TenantHotel, User

runner = CliRunner()


async def invoke(*args: str):  # type: ignore[no-untyped-def]
    # Test là async (pytest-asyncio) còn CLI gọi asyncio.run: chạy trong thread riêng.
    return await asyncio.to_thread(runner.invoke, app, list(args))


@pytest.fixture(autouse=True)
def _point_cli_at_test_db(migrated_db_url: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://u-{country}-{session}:p@h:1")
    from app.config import get_settings

    get_settings.cache_clear()


async def test_add_tenant_and_hotel(db: AsyncSession) -> None:
    r = await invoke(
        "add-tenant", "Khách sạn A", "--timezone", "Asia/Ho_Chi_Minh", "--horizon", "30"
    )
    assert r.exit_code == 0, r.output
    tenant = (await db.execute(select(Tenant))).scalar_one()
    assert tenant.name == "Khách sạn A" and tenant.scan_times == ["06:00", "14:00", "22:00"]

    r = await invoke(
        "add-hotel",
        str(tenant.id),
        "https://www.booking.com/hotel/vn/the-reverie-saigon.html?aid=1",
        "--role",
        "competitor",
        "--label",
        "Reverie",
    )
    assert r.exit_code == 0, r.output
    hotel = (await db.execute(select(Hotel))).scalar_one()
    listing = (await db.execute(select(Listing))).scalar_one()
    link = (await db.execute(select(TenantHotel))).scalar_one()
    assert hotel.country_code == "vn" and listing.hotel_id == hotel.id
    # Operator thêm qua CLI: tin URL, quét ngay (không chờ verify).
    assert (listing.channel, listing.listing_key, listing.status) == (
        "booking",
        "vn/the-reverie-saigon",
        "active",
    )
    assert "channel=booking key=vn/the-reverie-saigon" in r.output
    assert link.role == "competitor" and link.label == "Reverie"

    r = await invoke(
        "add-hotel",
        str(tenant.id),
        "https://www.booking.com/hotel/vn/the-reverie-saigon.html",
        "--role",
        "self",
    )
    assert r.exit_code == 0, r.output
    db.expire_all()  # CLI ghi bằng session khác, buộc đọc lại từ DB
    assert len((await db.execute(select(Hotel))).scalars().all()) == 1
    link = (await db.execute(select(TenantHotel))).scalar_one()
    assert link.role == "self"


async def test_add_hotel_rejects_bad_url(db: AsyncSession) -> None:
    await invoke("add-tenant", "T")
    tenant = (await db.execute(select(Tenant))).scalar_one()
    r = await invoke("add-hotel", str(tenant.id), "https://www.booking.com/searchresults.html")
    assert r.exit_code == 1 and "booking.com/hotel/vn/ten-khach-san.html" in r.output
    r = await invoke("add-hotel", str(tenant.id), "https://example.com/hotel/x")
    assert r.exit_code == 1 and "Chỉ hỗ trợ trang khách sạn trên Booking.com" in r.output


async def test_scan_now_creates_run_without_queue(db: AsyncSession) -> None:
    await invoke("add-tenant", "T")
    tenant = (await db.execute(select(Tenant))).scalar_one()
    await invoke("add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/x.html")
    r = await invoke("scan-now", "--no-enqueue")
    assert r.exit_code == 0, r.output
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.total_jobs == 1 and run.channel == "booking"
    assert run.trigger_key.startswith("manual:") and run.trigger_key.endswith(":booking")
    assert f"scan run {run.id} [booking] created with 1 jobs" in r.output


async def test_measure_capacity_enqueues_due_listings(db: AsyncSession, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.scheduler.queue import ArqJobQueue

    sent: list[tuple[int, str, bool]] = []

    class Recorder:
        async def enqueue_capacity(
            self, listing_id: int, channel: str, force: bool = False, defer_by: object = None
        ) -> None:
            sent.append((listing_id, channel, force))

        async def close(self) -> None:
            return None

    async def connect(_url: str) -> Recorder:
        return Recorder()

    monkeypatch.setattr(ArqJobQueue, "connect", staticmethod(connect))
    await invoke("add-tenant", "T")
    tenant = (await db.execute(select(Tenant))).scalar_one()
    await invoke("add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/x.html")
    listing = (await db.execute(select(Listing))).scalar_one()
    r = await invoke("measure-capacity")
    assert r.exit_code == 0, r.output
    assert sent == [(listing.id, "booking", False)]
    r = await invoke("measure-capacity", "--hotel-id", str(listing.hotel_id))
    assert r.exit_code == 0 and sent[-1] == (listing.id, "booking", True)
    # Khách sạn đã có số phòng: cron/CLI không đo nữa (trừ khi chỉ định --hotel-id).
    await db.execute(update(Hotel).where(Hotel.id == listing.hotel_id).values(rooms_total=40))
    await db.commit()
    r = await invoke("measure-capacity", "--force")
    assert r.exit_code == 0 and len(sent) == 2


async def test_add_user(db: AsyncSession) -> None:
    await invoke("add-tenant", "T")
    tenant = (await db.execute(select(Tenant))).scalar_one()
    r = await invoke(
        "add-user",
        "Admin@Example.com",
        "--password",
        "secret123",
        "--role",
        "tenant_admin",
        "--tenant-id",
        str(tenant.id),
    )
    assert r.exit_code == 0, r.output
    user = (await db.execute(select(User))).scalar_one()
    assert (
        user.email == "admin@example.com"
        and user.role == "tenant_admin"
        and user.tenant_id == tenant.id
    )
    assert user.password_hash.startswith("$argon2")
    r = await invoke("add-user", "op@example.com", "--password", "x", "--role", "operator")
    assert r.exit_code == 0, r.output
    r = await invoke("add-user", "v@example.com", "--password", "x", "--role", "viewer")
    assert r.exit_code == 1


async def test_rederive_stock_command_runs(db: AsyncSession) -> None:
    r = await invoke("rederive-stock", "--no-reanalyze")
    assert r.exit_code == 0, r.output
    assert "rederived=0 runs=0 reanalyzed_runs=0" in r.output


async def test_rederive_stock_reanalyzes_runs_without_changed_rooms(db: AsyncSession) -> None:
    """Đổi nghĩa exact_rooms_left (0016) cần tính lại MỌI run, kể cả run không có loại phòng nào đổi
    mức tin cậy; không thì ô cũ giữ tổng thiếu cũ mà không có khoảng min/max."""
    from datetime import UTC, date, datetime, timedelta
    from decimal import Decimal

    from app.db.models import HotelDateMetric
    from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
    from app.repo.snapshots import SnapshotRepository
    from tests.integration.seed import add_hotel, scan_run

    at = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
    stay = date(2026, 10, 5)
    hotel = await add_hotel(db, "vn/legacy")
    run = scan_run("legacy:booking", at, finished_at=at + timedelta(minutes=30))
    run.total_probes = 1
    db.add(run)
    await db.flush()
    offer = RoomOffer("1", "Deluxe", 2, 2, 2, (RatePlan("Std", Decimal(100), "VND", True, None),))
    result = ProbeResult(
        ProbeStatus.OK,
        ProbeMethod.HTTP,
        stay,
        stay + timedelta(days=1),
        1,
        2,
        (offer,),
        None,
        200,
        "s",
        10,
    )
    await SnapshotRepository(db, 10).write_probe(
        run.id, hotel.id, "booking", stay, result, None, "1", "vn", at
    )
    db.add(
        HotelDateMetric(
            hotel_id=hotel.id,
            channel="booking",
            stay_date=stay,
            as_of_scan_run_id=run.id,
            days_to_arrival=4,
            availability_status="available",
            exact_rooms_left=2,
            last_observed_at=at,
        )
    )
    await db.commit()

    r = await invoke("rederive-stock")
    assert r.exit_code == 0, r.output
    assert "reanalyzed_runs=1" in r.output
    db.expire_all()
    metric = (await db.execute(select(HotelDateMetric))).scalar_one()
    assert (metric.rooms_left_min, metric.rooms_left_max, metric.exact_rooms_left) == (2, 2, 2)
