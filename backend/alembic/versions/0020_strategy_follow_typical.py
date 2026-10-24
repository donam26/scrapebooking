"""chiến lược giá "giữ như hiện nay" theo mức giá thường của khách sạn (UX overhaul, Q2)

- price_strategies.follow_typical (bool, mặc định false): true = vị trí giá mục tiêu đi theo mức
  giá thường của khách sạn (trung vị chỉ số giá 30 đêm tới, tính lại mỗi ngày) thay cho
  target_index cố định, và gợi ý tăng/giảm vẫn cần tín hiệu cầu như khi chưa lưu chiến lược.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "price_strategies",
        sa.Column("follow_typical", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("price_strategies", "follow_typical")
