"""email notifications: recipients, per-tenant rules, outbox log

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.create_table(
        "notification_rules",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("params", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("dedupe_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text, nullable=False, server_default=""),
        sa.Column("body_html", sa.Text, nullable=False, server_default=""),
        sa.Column("recipients", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("detail", sa.Text),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id")),
        sa.Column("insight_id", sa.Integer, sa.ForeignKey("insights.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_tenant_created", "notifications", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_tenant_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_rules")
    op.drop_index("uq_notification_recipients_tenant_email", table_name="notification_recipients")
    op.drop_table("notification_recipients")
