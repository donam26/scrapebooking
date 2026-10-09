"""roadmap Phase 0–2: so cùng điều kiện (bữa sáng/chỉ phòng, khoá gói), hạn chế bán (min-stay,
trạng thái restricted), lý do sự kiện (lowest_rate_shift, nguyên nhân parity), radar KM

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _price_basis_cols(table: str) -> None:
    op.add_column(table, sa.Column("min_breakfast_price", sa.Numeric(14, 2)))
    op.add_column(table, sa.Column("min_room_only_price", sa.Numeric(14, 2)))
    op.add_column(table, sa.Column("min_stay", sa.Integer, nullable=False, server_default="1"))
    op.add_column(table, sa.Column("probe_status", sa.String(24)))


def upgrade() -> None:
    _price_basis_cols("hotel_date_snapshots")
    _price_basis_cols("hotel_date_metrics")
    op.add_column("hotel_date_metrics", sa.Column("cheapest_rate", postgresql.JSONB))
    op.add_column("hotel_date_metrics", sa.Column("prices_by_key", postgresql.JSONB))
    op.add_column("hotel_date_metrics", sa.Column("promos", postgresql.JSONB))
    op.add_column("availability_events", sa.Column("reason", sa.String(24)))
    op.add_column("availability_events", sa.Column("detail", postgresql.JSONB))
    op.create_index(
        "ix_availability_events_type_observed",
        "availability_events",
        ["event_type", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_availability_events_type_observed", table_name="availability_events")
    op.drop_column("availability_events", "detail")
    op.drop_column("availability_events", "reason")
    for col in ("promos", "prices_by_key", "cheapest_rate"):
        op.drop_column("hotel_date_metrics", col)
    for table in ("hotel_date_metrics", "hotel_date_snapshots"):
        for col in ("probe_status", "min_stay", "min_room_only_price", "min_breakfast_price"):
            op.drop_column(table, col)
