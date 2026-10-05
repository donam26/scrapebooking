"""market areas: thị trường toàn thành phố (khu vực, khách sạn của khu vực, lượt quét danh sách, giá
trên trang kết quả) + điểm/số review/ảnh/quận của khách sạn

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hotels", sa.Column("review_score", sa.Numeric(3, 1)))
    op.add_column("hotels", sa.Column("review_count", sa.Integer))
    op.add_column("hotels", sa.Column("image_url", sa.Text))
    op.add_column("hotels", sa.Column("district", sa.String(120)))

    op.create_table(
        "market_areas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(16), nullable=False, server_default="booking"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("dest_id", sa.String(32), nullable=False),
        sa.Column("dest_type", sa.String(16), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="vn"),
        sa.Column("list_nights", sa.Integer, nullable=False, server_default="14"),
        sa.Column("detail_horizon_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("detail_max_hotels", sa.Integer, nullable=False, server_default="300"),
        sa.Column("max_pages", sa.Integer, nullable=False, server_default="60"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("list_requested_at", sa.DateTime(timezone=True)),
        sa.Column("last_list_scan_at", sa.DateTime(timezone=True)),
        sa.Column("last_list_status", sa.String(16)),
        sa.Column("last_list_error", sa.Text),
        sa.Column("last_detail_scan_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_detail_run_id", sa.Integer, sa.ForeignKey("scan_runs.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id", "channel", "dest_type", "dest_id", name="uq_market_areas_dest"
        ),
        sa.CheckConstraint("detail_horizon_days BETWEEN 1 AND 90", name="ck_market_areas_horizon"),
        sa.CheckConstraint("list_nights BETWEEN 1 AND 30", name="ck_market_areas_list_nights"),
        sa.CheckConstraint("detail_max_hotels >= 0", name="ck_market_areas_max_hotels"),
        sa.CheckConstraint("max_pages BETWEEN 1 AND 100", name="ck_market_areas_max_pages"),
    )

    op.create_table(
        "market_area_hotels",
        sa.Column(
            "area_id",
            sa.Integer,
            sa.ForeignKey("market_areas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("best_rank", sa.Integer),
    )
    op.create_index("ix_market_area_hotels_hotel", "market_area_hotels", ["hotel_id"])

    op.create_table(
        "market_list_scans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "area_id",
            sa.Integer,
            sa.ForeignKey("market_areas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("properties_found", sa.Integer),
        sa.Column("pages", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hotels_seen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("priced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("error", sa.Text),
    )
    op.create_index(
        "ix_market_list_scans_area_date",
        "market_list_scans",
        ["area_id", "stay_date", "scanned_at"],
    )

    op.create_table(
        "market_list_prices",
        sa.Column(
            "scan_id",
            sa.Integer,
            sa.ForeignKey("market_list_scans.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
    )
    op.create_index("ix_market_list_prices_hotel", "market_list_prices", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_market_list_prices_hotel", table_name="market_list_prices")
    op.drop_table("market_list_prices")
    op.drop_index("ix_market_list_scans_area_date", table_name="market_list_scans")
    op.drop_table("market_list_scans")
    op.drop_index("ix_market_area_hotels_hotel", table_name="market_area_hotels")
    op.drop_table("market_area_hotels")
    op.drop_table("market_areas")
    op.drop_column("hotels", "district")
    op.drop_column("hotels", "image_url")
    op.drop_column("hotels", "review_count")
    op.drop_column("hotels", "review_score")
