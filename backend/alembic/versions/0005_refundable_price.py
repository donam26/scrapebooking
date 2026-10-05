"""hotel-level cheapest refundable price for like-for-like compset comparison

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL tới lượt quét kế tiếp: mỗi lượt cập nhật metrics cho mọi đêm trong horizon.
    op.add_column("hotel_date_snapshots", sa.Column("min_refundable_price", sa.Numeric(14, 2)))
    op.add_column("hotel_date_metrics", sa.Column("min_refundable_price", sa.Numeric(14, 2)))


def downgrade() -> None:
    op.drop_column("hotel_date_metrics", "min_refundable_price")
    op.drop_column("hotel_date_snapshots", "min_refundable_price")
