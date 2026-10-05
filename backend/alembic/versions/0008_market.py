"""market (wave 2): occupancy estimates per scan, estimated-run marker, price suggestion decisions

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "occupancy_estimates",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("channel", sa.String(16), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("days_to_arrival", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("inventory", sa.Integer, nullable=False),
        sa.Column("left_low", sa.Integer, nullable=False),
        sa.Column("left_high", sa.Integer, nullable=False),
        sa.Column("occ_low", sa.Numeric(5, 4), nullable=False),
        sa.Column("occ_high", sa.Numeric(5, 4), nullable=False),
        sa.Column("coverage", sa.Numeric(5, 4), nullable=False),
    )
    op.create_index(
        "ix_occupancy_estimates_hotel_date_time",
        "occupancy_estimates",
        ["hotel_id", "channel", "stay_date", "scanned_at"],
    )
    op.create_table(
        "occupancy_estimate_runs",
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "estimated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "price_suggestion_decisions",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("change_pct", sa.Integer, nullable=False),
        sa.Column("own_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("price_suggestion_decisions")
    op.drop_table("occupancy_estimate_runs")
    op.drop_index("ix_occupancy_estimates_hotel_date_time", table_name="occupancy_estimates")
    op.drop_table("occupancy_estimates")
