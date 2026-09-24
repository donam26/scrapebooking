from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.partitions import (
    drop_room_snapshot_partitions_older_than,
    ensure_room_snapshot_partitions,
    list_room_snapshot_partitions,
)

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenants", "hotels", "tenant_hotels", "room_types", "scan_runs", "scan_jobs",
    "probes", "hotel_calendars", "room_snapshots", "scrape_sessions",
    "hotel_date_snapshots", "availability_events", "hotel_date_metrics", "users",
    "insights", "own_hotel_daily", "pms_imports", "pms_column_mappings",
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
    dropped = await drop_room_snapshot_partitions_older_than(conn, keep_months=24, today=date(2026, 9, 24))
    assert set(dropped) >= {"room_snapshots_2020_01", "room_snapshots_2020_02"}
    remaining = await list_room_snapshot_partitions(conn)
    assert "room_snapshots_2020_01" not in remaining
    await db.commit()
