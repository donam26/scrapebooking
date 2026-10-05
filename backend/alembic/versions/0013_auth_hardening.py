"""bảo mật (phase 2): thu hồi phiên (users.token_version), hạn mức theo tenant (tenants.limits),
nhật ký thao tác (audit_events), token đặt lại mật khẩu (password_reset_tokens)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mọi JWT mang `tv`; tăng cột này (đổi mật khẩu, khoá, "đăng xuất mọi thiết bị") làm token cũ
    # mất hiệu lực ngay, không đợi hết hạn 12 giờ.
    op.add_column(
        "users", sa.Column("token_version", sa.Integer, nullable=False, server_default="0")
    )
    # Hạn mức riêng của tenant (max_hotels, manual_scans_per_day, insights_per_day…); thiếu khoá
    # thì dùng mặc định trong cấu hình.
    op.add_column(
        "tenants", sa.Column("limits", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("target", sa.String(120)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_audit_events_tenant_at", "audit_events", ["tenant_id", "at"])
    op.create_table(
        "password_reset_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_password_reset_tokens_user", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_audit_events_tenant_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_column("tenants", "limits")
    op.drop_column("users", "token_version")
