"""số phòng còn trung thực: trần dropdown theo listing, thang nbRooms của lịch, khoảng phòng còn
mức khách sạn, nguồn của số phòng công bố

- listings.dropdown_cap_seen: dropdown "chọn số phòng" lớn nhất từng thấy (Park Hyatt Saigon chỉ
  tới 9) → giá trị bằng mức này chỉ là "ít nhất".
- hotel_calendars.rooms_min/rooms_max: kết quả thang nbRooms của lịch GraphQL trong run (lịch
  trả lời "khách sạn còn ≥ N phòng?" cho cả cửa sổ đêm).
- hotel_date_snapshots/hotel_date_metrics.rooms_left_min/rooms_left_max: khoảng phòng còn của cả
  khách sạn; exact_rooms_left chỉ còn khi min = max.
- hotels.rooms_total_source/rooms_total_updated_at: số phòng công bố lấy từ đâu, khi nào.
- listings.rooms_max_seen/rooms_max_seen_at: Booking từng mở bán tối đa bao nhiêu phòng một đêm
  (sàn lớn nhất từng thấy) và lúc nào.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("dropdown_cap_seen", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("rooms_max_seen", sa.Integer(), nullable=True))
    op.add_column(
        "listings", sa.Column("rooms_max_seen_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("hotel_calendars", sa.Column("rooms_min", sa.Integer(), nullable=True))
    op.add_column("hotel_calendars", sa.Column("rooms_max", sa.Integer(), nullable=True))
    for table in ("hotel_date_snapshots", "hotel_date_metrics"):
        op.add_column(table, sa.Column("rooms_left_min", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("rooms_left_max", sa.Integer(), nullable=True))
    op.add_column("hotels", sa.Column("rooms_total_source", sa.Text(), nullable=True))
    op.add_column(
        "hotels", sa.Column("rooms_total_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    # exact_rooms_left cũ là tổng riêng các loại phòng chính xác (VD "2" cho khách sạn còn ≥72):
    # bỏ tới khi tính lại analytics (`sb rederive-stock`), không để giao diện hiện nó là số chắc.
    for table in ("hotel_date_snapshots", "hotel_date_metrics"):
        op.execute(f"UPDATE {table} SET exact_rooms_left = NULL WHERE rooms_left_min IS NULL")
    # Trần riêng từ dữ liệu đã có (giá trị thô dropdown_max được lưu ở mọi room snapshot).
    op.execute(
        "UPDATE listings l SET dropdown_cap_seen = s.cap "
        "FROM (SELECT hotel_id, channel, max(dropdown_max) AS cap FROM room_snapshots "
        "GROUP BY hotel_id, channel) s "
        "WHERE s.hotel_id = l.hotel_id AND s.channel = l.channel"
    )


def downgrade() -> None:
    op.drop_column("hotels", "rooms_total_updated_at")
    op.drop_column("hotels", "rooms_total_source")
    for table in ("hotel_date_metrics", "hotel_date_snapshots"):
        op.drop_column(table, "rooms_left_max")
        op.drop_column(table, "rooms_left_min")
    op.drop_column("hotel_calendars", "rooms_max")
    op.drop_column("hotel_calendars", "rooms_min")
    op.drop_column("listings", "rooms_max_seen_at")
    op.drop_column("listings", "rooms_max_seen")
    op.drop_column("listings", "dropdown_cap_seen")
