"""local events: sự kiện địa phương do tenant nhập (lễ hội, MICE, thể thao, mùa) cho lịch Terminal+

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("expected_uplift_pct", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_local_events_range"),
    )
    op.create_index("ix_local_events_tenant_start", "local_events", ["tenant_id", "start_date"])


def downgrade() -> None:
    op.drop_index("ix_local_events_tenant_start", table_name="local_events")
    op.drop_table("local_events")
