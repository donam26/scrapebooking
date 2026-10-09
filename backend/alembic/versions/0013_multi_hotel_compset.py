"""roadmap 5.5/5.6/7.3/7.5: compset theo từng khách sạn của bạn, compset chính/phụ, tổng số phòng
công bố, thị trường nguồn khách của tenant

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hotels", sa.Column("rooms_total", sa.Integer))
    op.add_column("tenant_hotels", sa.Column("compset_of", sa.Integer, sa.ForeignKey("hotels.id")))
    op.add_column(
        "tenant_hotels",
        sa.Column("tier", sa.String(16), nullable=False, server_default="primary"),
    )
    op.add_column(
        "tenant_hotels",
        sa.Column("weight", sa.Numeric(4, 2), nullable=False, server_default="1"),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "source_markets",
            postgresql.ARRAY(sa.String(2)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "source_markets")
    op.drop_column("tenant_hotels", "weight")
    op.drop_column("tenant_hotels", "tier")
    op.drop_column("tenant_hotels", "compset_of")
    op.drop_column("hotels", "rooms_total")
