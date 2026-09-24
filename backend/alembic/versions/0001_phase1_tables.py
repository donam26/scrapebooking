"""phase1 tables

Revision ID: 0001
Revises:
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("scan_times", postgresql.ARRAY(sa.String(5)), nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("insight_language", sa.String(8), nullable=False),
        sa.Column("insight_hour", sa.String(5), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "hotels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("booking_url", sa.Text, nullable=False),
        sa.Column("booking_slug", sa.String(200), nullable=False, unique=True),
        sa.Column("booking_hotel_id", sa.String(32)),
        sa.Column("name", sa.String(300)),
        sa.Column("city", sa.String(120)),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("star_rating", sa.Numeric(2, 1)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenant_hotels",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("label", sa.String(120)),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "room_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("booking_room_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("max_occupancy", sa.Integer),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("hotel_id", "booking_room_id"),
    )
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trigger_key", sa.String(32), nullable=False, unique=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_probes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sold_out_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "scan_jobs",
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "probes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("checkin", sa.Date, nullable=False),
        sa.Column("checkout", sa.Date, nullable=False),
        sa.Column("nights", sa.Integer, nullable=False),
        sa.Column("adults", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("method", sa.String(16)),
        sa.Column("proxy_country", sa.String(2)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("http_status", sa.Integer),
        sa.Column("raw_object_key", sa.Text),
        sa.Column("parser_version", sa.String(16)),
        sa.Column("error", sa.Text),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("scan_run_id", "hotel_id", "stay_date"),
    )
    op.create_index("ix_probes_hotel_date_fetched", "probes", ["hotel_id", "stay_date", "fetched_at"])
    op.create_table(
        "hotel_calendars",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("available", sa.Boolean, nullable=False),
        sa.Column("min_length_of_stay", sa.Integer, nullable=False, server_default="1"),
        sa.Column("avg_price_display", sa.String(64)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "room_snapshots",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column("probe_id", sa.BigInteger, sa.ForeignKey("probes.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("room_type_id", sa.Integer, sa.ForeignKey("room_types.id"), nullable=False),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rooms_left", sa.Integer),
        sa.Column("stock_confidence", sa.String(16), nullable=False),
        sa.Column("badge_count", sa.Integer),
        sa.Column("dropdown_max", sa.Integer),
        sa.Column("min_price", sa.Numeric(14, 2)),
        sa.Column("min_refundable_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("rates", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id", "scanned_at"),
        postgresql_partition_by="RANGE (scanned_at)",
    )
    op.create_index(
        "ix_room_snapshots_hotel_date_time",
        "room_snapshots",
        ["hotel_id", "stay_date", "scanned_at"],
    )
    op.execute(
        """
        DO $$
        DECLARE m date := date_trunc('month', now())::date;
        BEGIN
          FOR i IN 0..2 LOOP
            EXECUTE format(
              'CREATE TABLE IF NOT EXISTS room_snapshots_%s PARTITION OF room_snapshots '
              'FOR VALUES FROM (%L) TO (%L)',
              to_char(m + (i || ' month')::interval, 'YYYY_MM'),
              (m + (i || ' month')::interval)::date,
              (m + ((i + 1) || ' month')::interval)::date
            );
          END LOOP;
        END $$;
        """
    )
    op.create_table(
        "scrape_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("proxy_id", sa.String(128), nullable=False),
        sa.Column("proxy_country", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("block_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scrape_sessions")
    op.drop_table("room_snapshots")
    op.drop_table("hotel_calendars")
    op.drop_table("probes")
    op.drop_table("scan_jobs")
    op.drop_table("scan_runs")
    op.drop_table("room_types")
    op.drop_table("tenant_hotels")
    op.drop_table("hotels")
    op.drop_table("tenants")
