"""mời người dùng qua email, lần đăng nhập cuối, người nhập PMS (UX Phase 3, C5)

- users.invite_token_hash (varchar 64, null) + users.invite_expires_at (timestamptz, null): lời
  mời đặt mật khẩu dùng một lần, chỉ lưu sha256 của phần bí mật trong link, hết hạn sau 72 giờ.
  Người được mời có mật khẩu "không dùng được" (bắt đầu bằng "!") cho tới khi tự đặt.
- users.last_login_at (timestamptz, null): ghi khi đăng nhập thành công.
- pms_imports.created_by (FK users, ON DELETE SET NULL, null): ai nhập tệp PMS/OTB.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("invite_token_hash", sa.String(64), nullable=True))
    op.add_column(
        "users", sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("pms_imports", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pms_imports_created_by_users",
        "pms_imports",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_pms_imports_created_by_users", "pms_imports", type_="foreignkey")
    op.drop_column("pms_imports", "created_by")
    op.drop_column("users", "invite_expires_at")
    op.drop_column("users", "invite_token_hash")
    op.drop_column("users", "last_login_at")
