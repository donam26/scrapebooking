import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import Listing, ScanJob
from app.db.partitions import (
    drop_room_snapshot_partitions_older_than,
    ensure_room_snapshot_partitions,
    list_room_snapshot_partitions,
)
from tests.integration.seed import add_hotel, add_listing, scan_run

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenants",
    "hotels",
    "tenant_hotels",
    "room_types",
    "scan_runs",
    "scan_jobs",
    "probes",
    "hotel_calendars",
    "room_snapshots",
    "scrape_sessions",
    "hotel_date_snapshots",
    "availability_events",
    "hotel_date_metrics",
    "users",
    "insights",
    "own_hotel_daily",
    "pms_imports",
    "pms_column_mappings",
    "listings",
    "listing_demand_signals",
}


async def test_all_tables_exist(db: AsyncSession) -> None:
    rows = await db.execute(text("select tablename from pg_tables where schemaname='public'"))
    names = {r[0] for r in rows}
    assert EXPECTED_TABLES <= names


async def test_room_snapshots_is_partitioned_with_current_months(db: AsyncSession) -> None:
    rows = await db.execute(
        text(
            "select c.relname from pg_inherits i "
            "join pg_class c on c.oid = i.inhrelid "
            "join pg_class p on p.oid = i.inhparent where p.relname='room_snapshots'"
        )
    )
    parts = {r[0] for r in rows}
    assert len(parts) >= 3
    assert any(p.startswith("room_snapshots_") for p in parts)


async def test_ensure_partitions_creates_past_month(db: AsyncSession) -> None:
    conn = await db.connection()
    created = await ensure_room_snapshot_partitions(conn, first_month=date(2020, 1, 10), months=2)
    assert created == ["room_snapshots_2020_01", "room_snapshots_2020_02"]
    again = await ensure_room_snapshot_partitions(conn, first_month=date(2020, 1, 10), months=2)
    assert again == []
    await db.commit()


async def test_drop_old_partitions(db: AsyncSession) -> None:
    conn = await db.connection()
    await ensure_room_snapshot_partitions(conn, first_month=date(2020, 1, 10), months=2)
    dropped = await drop_room_snapshot_partitions_older_than(
        conn, keep_months=24, today=date(2026, 9, 24)
    )
    assert set(dropped) >= {"room_snapshots_2020_01", "room_snapshots_2020_02"}
    remaining = await list_room_snapshot_partitions(conn)
    assert "room_snapshots_2020_01" not in remaining
    await db.commit()


async def test_multi_channel_migration_round_trip_keeps_booking_data(
    db: AsyncSession, migrated_db_url: str
) -> None:
    """0007 xuống rồi lên lại: dữ liệu Booking giữ nguyên, kênh khác bị bỏ, khoá run dài (quét ngay
    sau đa kênh) vẫn vừa cột cũ."""
    hotel = await add_hotel(db, "vn/caravelle", name="Caravelle")
    booking = (await db.execute(select(Listing).where(Listing.hotel_id == hotel.id))).scalar_one()
    booking.external_id = "74331"
    await add_listing(db, hotel.id, "agoda", "caravelle-hotel")
    at = datetime(2026, 10, 1, 1, 15, tzinfo=UTC)
    kept = scan_run("manual:t12:20261001T081500:booking", at)
    dropped = scan_run("manual:t12:20261001T081500:agoda", at, channel="agoda")
    db.add_all([kept, dropped])
    await db.flush()
    db.add(ScanJob(scan_run_id=dropped.id, hotel_id=hotel.id, start_date=at.date(), horizon_days=1))
    kept_id = kept.id
    await db.commit()
    await db.close()
    await db.bind.dispose()  # type: ignore[union-attr]
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)

    await asyncio.to_thread(command.downgrade, cfg, "0006")
    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.connect() as conn:
            hotel_row = (
                await conn.execute(
                    text("select booking_slug, booking_hotel_id, booking_url from hotels")
                )
            ).one()
            runs = (await conn.execute(text("select id, trigger_key from scan_runs"))).all()
        assert tuple(hotel_row) == (
            "vn/caravelle",
            "74331",
            "https://www.booking.com/hotel/vn/caravelle.html",
        )
        assert [tuple(r) for r in runs] == [(kept_id, "manual:t12:20261001T081500")]
    finally:
        await engine.dispose()
        await asyncio.to_thread(command.upgrade, cfg, "head")

    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.connect() as conn:
            listings = (
                await conn.execute(
                    text("select channel, listing_key, external_id, status from listings")
                )
            ).all()
            run_channels = (await conn.execute(text("select channel from scan_runs"))).all()
        assert [tuple(r) for r in listings] == [("booking", "vn/caravelle", "74331", "active")]
        assert [r[0] for r in run_channels] == ["booking"]
    finally:
        await engine.dispose()
