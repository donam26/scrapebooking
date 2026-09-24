import asyncio
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.db.models import Hotel, ScanRun, Tenant, TenantHotel, User

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
    link = (await db.execute(select(TenantHotel))).scalar_one()
    assert hotel.booking_slug == "vn/the-reverie-saigon" and hotel.country_code == "vn"
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
    assert r.exit_code == 1 and "not a hotel page url" in r.output


async def test_scan_now_creates_run_without_queue(db: AsyncSession) -> None:
    await invoke("add-tenant", "T")
    tenant = (await db.execute(select(Tenant))).scalar_one()
    await invoke("add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/x.html")
    r = await invoke("scan-now", "--no-enqueue")
    assert r.exit_code == 0, r.output
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.total_jobs == 1 and run.trigger_key.startswith("manual:")


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
