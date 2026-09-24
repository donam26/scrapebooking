"""phase2 analytics tables and users

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hotel_date_snapshots",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("exact_rooms_left", sa.Integer),
        sa.Column("room_types_available", sa.Integer, nullable=False, server_default="0"),
        sa.Column("room_types_sold_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("min_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
    )
    op.create_index(
        "ix_hotel_date_snapshots_run", "hotel_date_snapshots", ["scan_run_id"]
    )
    op.create_table(
        "availability_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("room_type_id", sa.Integer, sa.ForeignKey("room_types.id")),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("from_value", sa.String(64)),
        sa.Column("to_value", sa.String(64)),
        sa.Column("delta", sa.Numeric(14, 2)),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("previous_scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id")),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scan_run_id", "hotel_id", "room_type_id", "stay_date", "event_type",
            name="uq_availability_events_run_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_availability_events_hotel_observed", "availability_events", ["hotel_id", "observed_at"]
    )
    op.create_index("ix_availability_events_stay_date", "availability_events", ["stay_date"])
    op.create_table(
        "hotel_date_metrics",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("as_of_scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("days_to_arrival", sa.Integer, nullable=False),
        sa.Column("pickup_24h", sa.Integer),
        sa.Column("velocity_3d", sa.Numeric(10, 3)),
        sa.Column("sold_out_at", sa.DateTime(timezone=True)),
        sa.Column("restocked_at", sa.DateTime(timezone=True)),
        sa.Column("min_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("price_change_7d_pct", sa.Numeric(8, 2)),
        sa.Column("availability_status", sa.String(16), nullable=False),
        sa.Column("exact_rooms_left", sa.Integer),
        sa.Column("exact_share", sa.Numeric(5, 4)),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id")),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("hotel_date_metrics")
    op.drop_table("availability_events")
    op.drop_table("hotel_date_snapshots")
