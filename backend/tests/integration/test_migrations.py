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


async def test_booking_only_migration_drops_other_channels(
    db: AsyncSession, migrated_db_url: str
) -> None:
    """0015: dữ liệu kênh khác Booking (listing, run, probe, sự kiện, tín hiệu cầu) bị xoá; dữ
    liệu Booking giữ nguyên; sự kiện chéo kênh và luật parity bị bỏ."""
    await db.close()
    await db.bind.dispose()  # type: ignore[union-attr]
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)
    await asyncio.to_thread(command.downgrade, cfg, "0014")
    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into tenants (id, name, timezone, scan_times, horizon_days, "
                    "insight_language, insight_hour, country_code, reference_channel, active) "
                    "values (1, 'T', 'Asia/Ho_Chi_Minh', '{06:00}', 30, 'vi', '07:30', 'vn', "
                    "'agoda', true)"
                )
            )
            await conn.execute(text("insert into hotels (id, country_code) values (1, 'vn')"))
            for lid, ch, key, status in (
                (1, "booking", "vn/x", "active"),
                (2, "agoda", "x-hotel", "active"),
                (3, "mytour", "x-mt", "suggested"),
            ):
                await conn.execute(
                    text(
                        "insert into listings (id, hotel_id, channel, listing_key, url, status) "
                        "values (:i, 1, :c, :k, 'https://x', :s)"
                    ),
                    {"i": lid, "c": ch, "k": key, "s": status},
                )
            for rid, ch in ((1, "booking"), (2, "agoda")):
                await conn.execute(
                    text(
                        "insert into scan_runs (id, trigger_key, channel, scheduled_at, status) "
                        "values (:i, :k, :c, now(), 'completed')"
                    ),
                    {"i": rid, "k": f"k:{ch}", "c": ch},
                )
                await conn.execute(
                    text(
                        "insert into probes (scan_run_id, hotel_id, channel, stay_date, checkin, "
                        "checkout, nights, adults, status, fetched_at) values (:r, 1, :c, "
                        "'2026-10-20', '2026-10-20', '2026-10-21', 1, 2, 'ok', now())"
                    ),
                    {"r": rid, "c": ch},
                )
            await conn.execute(
                text(
                    "insert into listing_demand_signals (hotel_id, channel, scan_run_id, kind, "
                    "value, observed_at) values (1, 'agoda', 2, 'bookings_24h', 13, now())"
                )
            )
            await conn.execute(
                text(
                    "insert into availability_events (hotel_id, channel, stay_date, event_type, "
                    "confidence, scan_run_id, observed_at) values "
                    "(1, 'booking', '2026-10-20', 'parity_gap', 'exact', 1, now()), "
                    "(1, 'booking', '2026-10-20', 'sold_out', 'exact', 1, now()), "
                    "(1, 'agoda', '2026-10-20', 'sold_out', 'exact', 2, now())"
                )
            )
            await conn.execute(
                text(
                    "insert into notification_rules (tenant_id, kind, active, params) values "
                    "(1, 'own_parity_gap', true, '{}'), (1, 'competitor_sold_out', true, '{}')"
                )
            )
            for iid, summary in ((1, "Booking: còn 2 phòng"), (2, "Giá rẻ hơn trên Agoda")):
                await conn.execute(
                    text(
                        "insert into insights (id, tenant_id, period_start, period_end, "
                        "generated_at, trigger, model, prompt_version, input_json) values "
                        "(:i, 1, '2026-10-01', '2026-10-30', now(), 'daily', 'm', '2', "
                        "jsonb_build_object('summary', cast(:s as text)))"
                    ),
                    {"i": iid, "s": summary},
                )
            await conn.execute(
                text(
                    "insert into notifications (id, tenant_id, kind, dedupe_key, status, "
                    "subject, insight_id) values "
                    "(1, 1, 'alerts', 'a1', 'sent', 'X đóng bán trên iVIVU', null), "
                    "(2, 1, 'daily_insight', 'i2', 'sent', 'Bản tin sáng', 2), "
                    "(3, 1, 'alerts', 'a3', 'sent', 'X hết phòng', null)"
                )
            )
    finally:
        await engine.dispose()
    await asyncio.to_thread(command.upgrade, cfg, "head")
    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.connect() as conn:
            q = {
                "listings": "select channel || ':' || status from listings",
                "runs": "select channel from scan_runs",
                "probes": "select channel from probes",
                "events": "select channel || ':' || event_type from availability_events",
                "rules": "select kind from notification_rules",
                "ref": "select reference_channel from tenants",
                "signals": "select to_regclass('listing_demand_signals')::text",
                "insights": "select id::text from insights",
                "notifs": "select id || ':' || coalesce(insight_id::text, '-') from notifications",
            }
            got = {
                k: sorted(r[0] for r in await conn.execute(text(v)) if r[0]) for k, v in q.items()
            }
        assert got == {
            "listings": ["booking:active"],
            "runs": ["booking"],
            "probes": ["booking"],
            "events": ["booking:sold_out"],
            "rules": ["competitor_sold_out"],
            "ref": ["booking"],
            "signals": [],
            "insights": ["1"],
            "notifs": ["2:-", "3:-"],
        }
    finally:
        await engine.dispose()
