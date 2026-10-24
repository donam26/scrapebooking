"""thị trường theo quận/bán kính + phân khúc + thang phòng trống (GraphQL FullSearch)

- market_areas: lat/lng (khu vực toạ độ `latlong`), radius_m (bộ lọc `distance` của Booking:
  1000/3000/5000, bắt buộc với `latlong`), segment_nflt (phân khúc, cú pháp nflt của Booking).
- market_list_scans: nguồn (graphql/ssr), bộ lọc phân khúc + bán kính lúc quét (`nflt`), số chỗ Booking
  nới thêm ngoài khu vực, cờ ít phòng,
  % đã kín Booking tự tính + số còn phòng + facet của truy vấn thị trường, facet + histogram giá của
  truy vấn phân khúc, thang `ladder` (JSONB), `enumerated` (đã liệt kê id ở mọi nấc).
- market_list_prices: rank cho phép NULL (khách sạn chỉ thấy ở trang sắp theo giá/thang), rooms_min
  (nấc lớn nhất còn bán được), only_left ("We have N left at this price").

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("market_areas", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("market_areas", sa.Column("lng", sa.Float(), nullable=True))
    op.add_column("market_areas", sa.Column("radius_m", sa.Integer(), nullable=True))
    op.add_column("market_areas", sa.Column("segment_nflt", sa.String(200), nullable=True))
    op.create_check_constraint(
        "ck_market_areas_radius",
        "market_areas",
        "radius_m IS NULL OR radius_m IN (1000, 3000, 5000)",
    )
    op.create_check_constraint(
        "ck_market_areas_latlong",
        "market_areas",
        "dest_type <> 'latlong' OR (lat IS NOT NULL AND lng IS NOT NULL AND radius_m IS NOT NULL)",
    )

    op.add_column("market_list_scans", sa.Column("source", sa.String(8), nullable=True))
    op.add_column("market_list_scans", sa.Column("nflt", sa.String(250), nullable=True))
    op.add_column("market_list_scans", sa.Column("autoextended", sa.Integer(), nullable=True))
    op.add_column("market_list_scans", sa.Column("low_availability", sa.Boolean(), nullable=True))
    op.add_column(
        "market_list_scans", sa.Column("unavailability_pct", sa.SmallInteger(), nullable=True)
    )
    op.add_column("market_list_scans", sa.Column("market_available", sa.Integer(), nullable=True))
    for name in ("market_facets", "facets", "price_histogram", "ladder"):
        op.add_column(
            "market_list_scans",
            sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    op.add_column(
        "market_list_scans",
        sa.Column("enumerated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.alter_column("market_list_prices", "rank", existing_type=sa.Integer(), nullable=True)
    op.add_column("market_list_prices", sa.Column("rooms_min", sa.SmallInteger(), nullable=True))
    op.add_column("market_list_prices", sa.Column("only_left", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("market_list_prices", "only_left")
    op.drop_column("market_list_prices", "rooms_min")
    op.execute("UPDATE market_list_prices SET rank = 0 WHERE rank IS NULL")
    op.alter_column("market_list_prices", "rank", existing_type=sa.Integer(), nullable=False)

    for name in (
        "enumerated",
        "ladder",
        "price_histogram",
        "facets",
        "market_facets",
        "market_available",
        "unavailability_pct",
        "low_availability",
        "autoextended",
        "nflt",
        "source",
    ):
        op.drop_column("market_list_scans", name)

    op.execute("DELETE FROM market_areas WHERE dest_type = 'latlong'")
    op.drop_constraint("ck_market_areas_latlong", "market_areas", type_="check")
    op.drop_constraint("ck_market_areas_radius", "market_areas", type_="check")
    op.drop_column("market_areas", "segment_nflt")
    op.drop_column("market_areas", "radius_m")
    op.drop_column("market_areas", "lng")
    op.drop_column("market_areas", "lat")
