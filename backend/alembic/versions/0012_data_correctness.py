"""đúng dữ liệu (phase 1): đếm not_found liên tiếp của listing, giữ giá cuối khi probe lỗi
(stale_since), gợi ý giá theo từng khách sạn self (hotel_id vào khoá), bỏ trạng thái batch_pending

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Listing chỉ bị đánh `broken` sau N lần not_found liên tiếp qua session khác nhau (soft block
    # trả 200 không còn giết listing).
    op.add_column(
        "listings",
        sa.Column("not_found_count", sa.Integer, nullable=False, server_default="0"),
    )

    # Probe bị chặn/lỗi không xoá giá cuối cùng trên heatmap: giữ giá, ghi từ lúc nào dữ liệu cũ.
    op.add_column(
        "hotel_date_metrics", sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True)
    )

    # Gợi ý giá theo từng khách sạn "self" (tenant chuỗi có nhiều cơ sở). Dòng cũ gán cho khách sạn
    # self nhỏ nhất của tenant; tenant không còn khách sạn self thì bỏ dòng.
    op.add_column(
        "price_suggestion_decisions",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=True),
    )
    op.execute(
        "UPDATE price_suggestion_decisions d SET hotel_id = s.hotel_id FROM ("
        " SELECT tenant_id, min(hotel_id) AS hotel_id FROM tenant_hotels"
        " WHERE role = 'self' AND active GROUP BY tenant_id) s"
        " WHERE d.tenant_id = s.tenant_id"
    )
    op.execute("DELETE FROM price_suggestion_decisions WHERE hotel_id IS NULL")
    op.alter_column("price_suggestion_decisions", "hotel_id", nullable=False)
    op.drop_constraint(
        "price_suggestion_decisions_pkey", "price_suggestion_decisions", type_="primary"
    )
    op.create_primary_key(
        "price_suggestion_decisions_pkey",
        "price_suggestion_decisions",
        ["tenant_id", "hotel_id", "stay_date", "kind"],
    )

    # Batch giả lập (OpenRouter không có Batch API) bị bỏ: dòng đang chờ coi như thất bại để cron
    # daily tạo lại bản tin đồng bộ.
    op.execute(
        "UPDATE insights SET status = 'failed', error = 'batch mode removed'"
        " WHERE status = 'batch_pending'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "price_suggestion_decisions_pkey", "price_suggestion_decisions", type_="primary"
    )
    # Khoá cũ không có hotel_id: giữ một dòng mỗi (tenant, đêm, loại).
    op.execute(
        "DELETE FROM price_suggestion_decisions d USING price_suggestion_decisions o"
        " WHERE d.tenant_id = o.tenant_id AND d.stay_date = o.stay_date AND d.kind = o.kind"
        " AND d.hotel_id > o.hotel_id"
    )
    op.create_primary_key(
        "price_suggestion_decisions_pkey",
        "price_suggestion_decisions",
        ["tenant_id", "stay_date", "kind"],
    )
    op.drop_column("price_suggestion_decisions", "hotel_id")
    op.drop_column("hotel_date_metrics", "stale_since")
    op.drop_column("listings", "not_found_count")
