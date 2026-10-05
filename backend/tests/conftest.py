import asyncio
import os
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.partitions import ensure_room_snapshot_partitions

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALL_TABLES = (
    "notifications, notification_rules, notification_recipients, listing_demand_signals, listings, "
    "availability_events, hotel_date_metrics, hotel_date_snapshots, insights, "
    "own_hotel_daily, pms_imports, pms_column_mappings, users, "
    "room_snapshots, hotel_calendars, probes, scan_jobs, scan_runs, room_types, "
    "tenant_hotels, hotels, tenants, scrape_sessions"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        if "/tests/live/" in path:
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    async def _ping() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_ping())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"test database unavailable at {TEST_DB_URL}: {exc}")
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # Migration chỉ tạo partition room_snapshots từ tháng hiện tại; dữ liệu test cố định ở
    # 09–10/2026 nên cần partition riêng, không phụ thuộc ngày chạy hay thứ tự test.
    async def _fixed_partitions() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            async with engine.begin() as conn:
                await ensure_room_snapshot_partitions(conn, first_month=date(2026, 9, 1), months=4)
        finally:
            await engine.dispose()

    asyncio.run(_fixed_partitions())
    return TEST_DB_URL


@pytest.fixture
async def db(migrated_db_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {ALL_TABLES} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
