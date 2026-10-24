"""thẻ "Thiết lập 5 bước" và một mô hình người nhận (UX Phase 3, C1–C2)

- tenants.setup_state (JSONB, mặc định {}): trạng thái thẻ thiết lập trên Hôm nay
  (`dismissed_at`: người quản trị bấm "Ẩn").
- notification_recipients gộp vào notification_subscriptions: mỗi người nhận email thành một đăng ký
  email nhận mọi loại tin (alerts, daily_insight, weekly_report, data_stale), không giờ im lặng,
  không trần tin/ngày, giữ trạng thái bật/tắt, không gắn người dùng (user_id NULL). Địa chỉ đã có
  đăng ký email thì đăng ký đó nhận mọi loại tin (như trước: danh sách người nhận nhận mọi email).
  Bảng notification_recipients bị xoá; gửi tin chỉ đọc đăng ký.

Downgrade: dựng lại bảng người nhận, đưa các đăng ký email không gắn người dùng về người nhận và xoá
chúng khỏi đăng ký; bỏ cột setup_state.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL_KINDS = "{alerts,daily_insight,weekly_report,data_stale}"


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "setup_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        f"""
        INSERT INTO notification_subscriptions (tenant_id, user_id, channel, target, kinds, active,
                                                created_at)
        SELECT tenant_id, NULL, 'email', email, '{ALL_KINDS}', active, created_at
        FROM notification_recipients
        ORDER BY id
        ON CONFLICT (tenant_id, channel, lower(target)) DO UPDATE
        SET kinds = EXCLUDED.kinds,
            active = notification_subscriptions.active OR EXCLUDED.active
        """
    )
    op.drop_index("uq_notification_recipients_tenant_email", table_name="notification_recipients")
    op.drop_table("notification_recipients")


def downgrade() -> None:
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_notification_recipients_tenant_email",
        "notification_recipients",
        ["tenant_id", sa.text("lower(email)")],
        unique=True,
    )
    op.execute(
        """
        INSERT INTO notification_recipients (tenant_id, email, active, created_at)
        SELECT tenant_id, left(target, 254), active, created_at
        FROM notification_subscriptions
        WHERE channel = 'email' AND user_id IS NULL
        ORDER BY id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute("DELETE FROM notification_subscriptions WHERE channel = 'email' AND user_id IS NULL")
    op.drop_column("tenants", "setup_state")
