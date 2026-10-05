"""multi-channel: listings (hotel × channel), channel on observation tables, demand signals

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

Khoá listing = (hotel_id, channel). Mỗi scan run thuộc một kênh nên scan_jobs/probes/
hotel_date_snapshots giữ khoá cũ; bảng cần phân biệt kênh thêm cột `channel`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHANNEL_TABLES = (
    "scan_runs",
    "probes",
    "room_types",
    "room_snapshots",
    "hotel_date_snapshots",
    "hotel_date_metrics",
    "availability_events",
)


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("listing_key", sa.String(300), nullable=False),
        sa.Column("external_id", sa.String(64)),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("name", sa.String(300)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("match_score", sa.Numeric(4, 3)),
        sa.Column("last_error", sa.Text),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("hotel_id", "channel", name="uq_listings_hotel_channel"),
        sa.UniqueConstraint("channel", "listing_key", name="uq_listings_channel_key"),
    )
    op.execute(
        "INSERT INTO listings (hotel_id, channel, listing_key, external_id, url, name, status,"
        " verified_at, created_at)"
        " SELECT id, 'booking', booking_slug, booking_hotel_id, booking_url, name, 'active',"
        " CASE WHEN booking_hotel_id IS NOT NULL THEN now() END, created_at FROM hotels"
    )
    op.add_column("hotels", sa.Column("address", sa.Text))
    op.add_column("hotels", sa.Column("lat", sa.Float))
    op.add_column("hotels", sa.Column("lng", sa.Float))
    op.drop_column("hotels", "booking_url")
    op.drop_column("hotels", "booking_slug")
    op.drop_column("hotels", "booking_hotel_id")

    for table in CHANNEL_TABLES:
        op.add_column(
            table,
            sa.Column("channel", sa.String(16), nullable=False, server_default="booking"),
        )
        op.alter_column(table, "channel", server_default=None)
    op.alter_column("scan_runs", "trigger_key", type_=sa.String(64))

    op.alter_column("room_types", "booking_room_id", new_column_name="external_room_id")
    op.drop_constraint("room_types_hotel_id_booking_room_id_key", "room_types", type_="unique")
    op.create_unique_constraint(
        "uq_room_types_listing_room", "room_types", ["hotel_id", "channel", "external_room_id"]
    )
    op.add_column(
        "room_snapshots",
        sa.Column("stock_scope", sa.String(16), nullable=False, server_default="room_type"),
    )
    op.drop_constraint("hotel_date_metrics_pkey", "hotel_date_metrics", type_="primary")
    op.create_primary_key(
        "hotel_date_metrics_pkey", "hotel_date_metrics", ["hotel_id", "channel", "stay_date"]
    )
    op.create_index(
        "ix_probes_hotel_channel_date", "probes", ["hotel_id", "channel", "stay_date", "fetched_at"]
    )

    op.create_table(
        "listing_demand_signals",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id")),
        sa.Column("stay_date", sa.Date),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("value", sa.Numeric(14, 3), nullable=False),
        sa.Column("window_hours", sa.Integer),
        sa.Column("raw_text", sa.Text),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_listing_demand_signals_hotel_observed",
        "listing_demand_signals",
        ["hotel_id", "channel", "observed_at"],
    )

    op.add_column(
        "tenants",
        sa.Column("reference_channel", sa.String(16), nullable=False, server_default="booking"),
    )
    # D12: horizon 90 đêm (quét theo tầng giữ số request gần như cũ). Chỉ đổi tenant đang ở mặc
    # định cũ 30; tenant tự đặt khác thì giữ.
    op.execute("UPDATE tenants SET horizon_days = 90 WHERE horizon_days = 30")


def downgrade() -> None:
    op.execute("UPDATE tenants SET horizon_days = 30 WHERE horizon_days = 90")
    op.drop_column("tenants", "reference_channel")
    op.drop_index("ix_listing_demand_signals_hotel_observed", "listing_demand_signals")
    op.drop_table("listing_demand_signals")
    op.drop_index("ix_probes_hotel_channel_date", "probes")

    # Dữ liệu kênh khác Booking không có chỗ trong schema cũ: xoá trước khi bỏ cột.
    for table in (
        "availability_events",
        "hotel_date_metrics",
        "hotel_date_snapshots",
        "room_snapshots",
    ):
        op.execute(f"DELETE FROM {table} WHERE channel <> 'booking'")
    op.execute(
        "DELETE FROM hotel_calendars WHERE scan_run_id IN"
        " (SELECT id FROM scan_runs WHERE channel <> 'booking')"
    )
    op.execute("DELETE FROM probes WHERE channel <> 'booking'")
    op.execute(
        "DELETE FROM scan_jobs WHERE scan_run_id IN (SELECT id FROM scan_runs WHERE channel <> 'booking')"
    )
    op.execute("DELETE FROM room_types WHERE channel <> 'booking'")
    # Run của kênh khác không còn dữ liệu; run Booking bỏ hậu tố ":booking" về khoá cũ (khoá
    # "manual:t1:<giờ>:booking" dài hơn 32 ký tự của cột cũ).
    for table in ("notifications", "insights"):
        op.execute(
            f"UPDATE {table} SET scan_run_id = NULL WHERE scan_run_id IN"
            " (SELECT id FROM scan_runs WHERE channel <> 'booking')"
        )
    op.execute("DELETE FROM scan_runs WHERE channel <> 'booking'")
    op.execute(
        "UPDATE scan_runs s SET trigger_key = left(s.trigger_key, length(s.trigger_key) - 8)"
        " WHERE s.trigger_key LIKE '%\\:booking' AND NOT EXISTS (SELECT 1 FROM scan_runs o"
        " WHERE o.trigger_key = left(s.trigger_key, length(s.trigger_key) - 8))"
    )
    op.drop_constraint("hotel_date_metrics_pkey", "hotel_date_metrics", type_="primary")
    op.create_primary_key(
        "hotel_date_metrics_pkey", "hotel_date_metrics", ["hotel_id", "stay_date"]
    )
    op.drop_column("room_snapshots", "stock_scope")
    op.drop_constraint("uq_room_types_listing_room", "room_types", type_="unique")
    op.alter_column("room_types", "external_room_id", new_column_name="booking_room_id")
    op.create_unique_constraint(
        "room_types_hotel_id_booking_room_id_key", "room_types", ["hotel_id", "booking_room_id"]
    )
    op.alter_column("scan_runs", "trigger_key", type_=sa.String(32))
    for table in CHANNEL_TABLES:
        op.drop_column(table, "channel")

    op.add_column("hotels", sa.Column("booking_url", sa.Text))
    op.add_column("hotels", sa.Column("booking_slug", sa.String(200)))
    op.add_column("hotels", sa.Column("booking_hotel_id", sa.String(32)))
    op.execute(
        "UPDATE hotels h SET booking_url = l.url, booking_slug = l.listing_key,"
        " booking_hotel_id = l.external_id FROM listings l"
        " WHERE l.hotel_id = h.id AND l.channel = 'booking'"
    )
    op.create_unique_constraint("hotels_booking_slug_key", "hotels", ["booking_slug"])
    op.drop_column("hotels", "lng")
    op.drop_column("hotels", "lat")
    op.drop_column("hotels", "address")
    op.drop_table("listings")
