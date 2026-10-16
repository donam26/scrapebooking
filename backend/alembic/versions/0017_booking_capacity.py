"""gợi ý "Số phòng" đo trên Booking.com: số phòng Booking bán nhiều nhất trong một đêm

- listings.capacity_max: kết quả lớn nhất của các lần đo lịch nbRooms trên các đêm xa (≤ 100).
- listings.capacity_capped: còn bán ở trần đo 100 → khách sạn có thể lớn hơn (chỉ là cận dưới).
- listings.capacity_checked_at: lần đo xong gần nhất.
- listings.capacity_next_at: lúc được đo lại (đo xong: 30 ngày; cửa sổ không có phòng: 7 ngày;
  đo dở vì lịch lỗi/bị chặn: 1 ngày); NULL = chưa đo lần nào.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("capacity_max", sa.Integer(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("capacity_capped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "listings", sa.Column("capacity_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "listings", sa.Column("capacity_next_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("listings", "capacity_next_at")
    op.drop_column("listings", "capacity_checked_at")
    op.drop_column("listings", "capacity_capped")
    op.drop_column("listings", "capacity_max")
