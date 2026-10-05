"""room_types.external_room_id 32 → 200 (iVIVU định danh loại phòng nguồn ngoài theo tên)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("room_types", "external_room_id", type_=sa.String(200))


def downgrade() -> None:
    # Giữ dòng (đang được snapshot/sự kiện tham chiếu): rút mã dài về md5 32 ký tự.
    op.execute(
        "UPDATE room_types SET external_room_id = md5(external_room_id) "
        "WHERE length(external_room_id) > 32"
    )
    op.alter_column("room_types", "external_room_id", type_=sa.String(32))
