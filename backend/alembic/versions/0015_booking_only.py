"""chỉ giữ Booking.com: xoá dữ liệu của mọi kênh khác (Agoda, iVIVU, Trip.com, Mytour…), sự kiện
chéo kênh (parity_gap, channel_closed), luật cảnh báo parity, bảng tín hiệu cầu của kênh; đặt kênh
tham chiếu của mọi tenant về booking

Dữ liệu bị xoá không khôi phục được: downgrade chỉ dựng lại bảng rỗng. Backup bằng `sb backup-db`
/ pg_dump trước khi chạy.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OTHER = "channel <> 'booking'"
OTHER_RUNS = f"SELECT id FROM scan_runs WHERE {OTHER}"
_OTAS = r"'agoda|ivivu|mytour|trip\.com|tripcom|traveloka|expedia'"
_STALE_NOTIFS = (
    "SELECT id FROM notifications WHERE "
    f"coalesce(subject, '') || coalesce(body_text, '') ~* {_OTAS}"
)
_STALE_INSIGHTS = f"SELECT i.id FROM insights i WHERE i::text ~* {_OTAS}"


def upgrade() -> None:
    # Tín hiệu cầu chỉ đến từ các kênh đã bỏ (có FK tới scan_runs): bỏ bảng trước.
    op.drop_table("listing_demand_signals")
    # Sự kiện: của kênh khác, và sự kiện chéo kênh còn lại trên Booking.
    op.execute(
        f"DELETE FROM availability_events WHERE {OTHER} "
        "OR event_type IN ('parity_gap', 'channel_closed') "
        f"OR scan_run_id IN ({OTHER_RUNS}) OR previous_scan_run_id IN ({OTHER_RUNS})"
    )
    op.execute(f"DELETE FROM hotel_date_metrics WHERE {OTHER}")
    op.execute(f"DELETE FROM hotel_date_snapshots WHERE {OTHER}")
    op.execute(f"DELETE FROM occupancy_estimates WHERE {OTHER}")
    op.execute(f"DELETE FROM occupancy_estimate_runs WHERE scan_run_id IN ({OTHER_RUNS})")
    op.execute(f"DELETE FROM room_snapshots WHERE {OTHER}")
    op.execute(f"DELETE FROM probes WHERE {OTHER}")
    op.execute(f"DELETE FROM hotel_calendars WHERE scan_run_id IN ({OTHER_RUNS})")
    op.execute(f"DELETE FROM scan_jobs WHERE scan_run_id IN ({OTHER_RUNS})")
    op.execute(f"UPDATE insights SET scan_run_id = NULL WHERE scan_run_id IN ({OTHER_RUNS})")
    op.execute(f"UPDATE notifications SET scan_run_id = NULL WHERE scan_run_id IN ({OTHER_RUNS})")
    op.execute(
        f"UPDATE market_areas SET last_detail_run_id = NULL "
        f"WHERE last_detail_run_id IN ({OTHER_RUNS})"
    )
    op.execute(f"DELETE FROM scan_runs WHERE {OTHER}")
    op.execute(f"DELETE FROM room_types WHERE {OTHER}")
    op.execute(f"DELETE FROM hotel_review_snapshots WHERE {OTHER}")
    op.execute(f"DELETE FROM listings WHERE {OTHER}")
    # Gợi ý listing chờ xác nhận (luồng tìm khách sạn trên kênh khác) không còn.
    op.execute("DELETE FROM listings WHERE status IN ('suggested', 'rejected')")
    # Bản tin AI và nhật ký thông báo (chưa từng gửi được hoặc đã gửi) nói về kênh đã bỏ: bằng
    # chứng của chúng trỏ tới sự kiện vừa xoá, giữ lại chỉ gây nhầm.
    op.execute(f"DELETE FROM notification_deliveries WHERE notification_id IN ({_STALE_NOTIFS})")
    op.execute(f"DELETE FROM notifications WHERE id IN ({_STALE_NOTIFS})")
    op.execute(
        f"UPDATE notifications SET insight_id = NULL WHERE insight_id IN ({_STALE_INSIGHTS})"
    )
    op.execute(f"DELETE FROM insights WHERE id IN ({_STALE_INSIGHTS})")
    op.execute("DELETE FROM notification_rules WHERE kind = 'own_parity_gap'")
    op.execute("UPDATE tenants SET reference_channel = 'booking'")
    op.execute("UPDATE market_areas SET channel = 'booking'")


def downgrade() -> None:
    # Chỉ dựng lại schema (bảng rỗng); dữ liệu các kênh khác phải khôi phục từ backup.
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
