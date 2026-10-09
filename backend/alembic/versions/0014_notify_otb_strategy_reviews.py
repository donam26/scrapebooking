"""roadmap Phase 3/5/6/7: kênh gửi + đăng ký theo người + nhật ký giao tin (Zalo/webhook), OTB theo
ngày, chiến lược giá RMS-lite, điểm review theo ngày, huy hiệu/quảng cáo trên trang kết quả

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 3: kênh gửi, đã xử lý, đăng ký theo người, nhật ký giao tin.
    op.add_column(
        "notifications",
        sa.Column("channel", sa.String(16), nullable=False, server_default="email"),
    )
    op.add_column("notifications", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column(
        "notifications",
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("kinds", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column("quiet_start", sa.String(5)),
        sa.Column("quiet_end", sa.String(5)),
        sa.Column("max_per_day", sa.Integer),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_notification_subscriptions_target",
        "notification_subscriptions",
        ["tenant_id", "channel", sa.text("lower(target)")],
        unique=True,
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.BigInteger,
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(128)),
        sa.Column("cost_vnd", sa.Numeric(10, 2)),
        sa.Column("error", sa.Text),
        sa.Column("token", sa.String(48), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("clicked_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_notification_deliveries_target_created",
        "notification_deliveries",
        ["channel", "target", "created_at"],
    )

    # Phase 5: OTB theo ngày.
    op.create_table(
        "otb_snapshots",
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("as_of_date", sa.Date, primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("rooms_otb", sa.Integer, nullable=False),
        sa.Column("revenue_otb", sa.Numeric(16, 2)),
        sa.Column("rooms_available", sa.Integer),
        sa.Column("cancellations", sa.Integer),
        sa.Column("group_rooms", sa.Integer),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_otb_snapshots_hotel_stay",
        "otb_snapshots",
        ["tenant_id", "hotel_id", "stay_date", "as_of_date"],
    )

    # Phase 6: chiến lược giá, nhật ký quyết định đầy đủ hơn.
    op.create_table(
        "price_strategies",
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("base_price", sa.Numeric(14, 2)),
        sa.Column("floor_price", sa.Numeric(14, 2)),
        sa.Column("ceiling_price", sa.Numeric(14, 2)),
        sa.Column("target_index", sa.Numeric(5, 1), nullable=False, server_default="100"),
        sa.Column("round_to", sa.Integer, nullable=False, server_default="10000"),
        sa.Column("max_daily_change_pct", sa.Integer, nullable=False, server_default="15"),
        sa.Column("weekday_adj", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("holiday_uplift_pct", sa.Integer, nullable=False, server_default="10"),
        sa.Column("last_minute_days", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_minute_adj_pct", sa.Integer, nullable=False, server_default="-5"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.add_column(
        "price_suggestion_decisions",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id")),
    )
    op.add_column("price_suggestion_decisions", sa.Column("target_price", sa.Numeric(14, 2)))
    op.add_column("price_suggestion_decisions", sa.Column("applied_price", sa.Numeric(14, 2)))
    op.add_column("price_suggestion_decisions", sa.Column("reasons", postgresql.JSONB))

    # Phase 7: review theo ngày, huy hiệu/quảng cáo trên trang kết quả.
    op.create_table(
        "hotel_review_snapshots",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("channel", sa.String(16), primary_key=True),
        sa.Column("observed_on", sa.Date, primary_key=True),
        sa.Column("review_score", sa.Numeric(3, 1)),
        sa.Column("review_count", sa.Integer),
        sa.Column("badges", postgresql.JSONB),
        sa.Column("preferred", sa.Boolean),
    )
    op.add_column("market_list_prices", sa.Column("sponsored", sa.Boolean))
    op.add_column("market_list_prices", sa.Column("badges", postgresql.JSONB))
    # Điểm đầu của chuỗi review: số mới nhất đang có trên bảng khách sạn.
    op.execute(
        "INSERT INTO hotel_review_snapshots (hotel_id, channel, observed_on, review_score, "
        "review_count) SELECT id, 'booking', current_date, review_score, review_count "
        "FROM hotels WHERE review_count IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("market_list_prices", "badges")
    op.drop_column("market_list_prices", "sponsored")
    op.drop_table("hotel_review_snapshots")
    for col in ("reasons", "applied_price", "target_price", "hotel_id"):
        op.drop_column("price_suggestion_decisions", col)
    op.drop_table("price_strategies")
    op.drop_index("ix_otb_snapshots_hotel_stay", table_name="otb_snapshots")
    op.drop_table("otb_snapshots")
    op.drop_index("ix_notification_deliveries_target_created", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("uq_notification_subscriptions_target", table_name="notification_subscriptions")
    op.drop_table("notification_subscriptions")
    op.drop_column("notifications", "resolved_by")
    op.drop_column("notifications", "resolved_at")
    op.drop_column("notifications", "channel")
