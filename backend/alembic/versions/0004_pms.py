"""phase4 pms import tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "own_hotel_daily",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("rooms_total", sa.Integer),
        sa.Column("rooms_sold", sa.Integer),
        sa.Column("rooms_available", sa.Integer),
        sa.Column("occupancy_pct", sa.Numeric(5, 2)),
        sa.Column("adr", sa.Numeric(14, 2)),
        sa.Column("revenue", sa.Numeric(16, 2)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pms_imports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("adapter", sa.String(32), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "pms_column_mappings",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("adapter", sa.String(32), primary_key=True),
        sa.Column("mapping", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pms_column_mappings")
    op.drop_table("pms_imports")
    op.drop_table("own_hotel_daily")
