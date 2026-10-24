"""Bảng thị trường toàn thành phố (migration 0011). Dùng chung `Base` nên Alembic và test vẫn thấy.

Khu vực thuộc một tenant; khách sạn (`hotels`) dùng chung toàn hệ thống như mọi nơi khác. Khách sạn
thị trường chỉ hiện ở tổng quan/compset của tenant khi tenant tự thêm vào watchlist.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class MarketArea(Base):
    """Khu vực trên một kênh mà tenant theo dõi cả chợ: thành phố/quận/vùng/địa danh (dest_id và
    dest_type của Booking) hoặc một điểm toạ độ (`latlong`, dest_id = "lat,lng") kèm bán kính; tuỳ
    chọn lọc theo phân khúc (`segment_nflt`)."""

    __tablename__ = "market_areas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "channel", "dest_type", "dest_id", name="uq_market_areas_dest"
        ),
        CheckConstraint("detail_horizon_days BETWEEN 1 AND 90", name="ck_market_areas_horizon"),
        CheckConstraint("list_nights BETWEEN 1 AND 30", name="ck_market_areas_list_nights"),
        CheckConstraint("detail_max_hotels >= 0", name="ck_market_areas_max_hotels"),
        CheckConstraint("max_pages BETWEEN 1 AND 100", name="ck_market_areas_max_pages"),
        CheckConstraint(
            "radius_m IS NULL OR radius_m IN (1000, 3000, 5000)", name="ck_market_areas_radius"
        ),
        CheckConstraint(
            "dest_type <> 'latlong' "
            "OR (lat IS NOT NULL AND lng IS NOT NULL AND radius_m IS NOT NULL)",
            name="ck_market_areas_latlong",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16), default="booking")
    name: Mapped[str] = mapped_column(String(200))
    dest_id: Mapped[str] = mapped_column(String(32))
    # city | district | region | landmark | latlong
    dest_type: Mapped[str] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="vn")
    # Tâm của khu vực `latlong` (thường là khách sạn của tenant).
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    # Bán kính quanh tâm: bộ lọc `distance` của Booking (1000/3000/5000 m); bắt buộc với `latlong`.
    radius_m: Mapped[int | None] = mapped_column(Integer)
    # Phân khúc: bộ lọc Booking dạng nflt ("ht_id=204;ht_id=206"); None = mọi loại chỗ ở.
    segment_nflt: Mapped[str | None] = mapped_column(String(200))
    list_nights: Mapped[int] = mapped_column(Integer, default=14)
    detail_horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    detail_max_hotels: Mapped[int] = mapped_column(Integer, default=300)
    max_pages: Mapped[int] = mapped_column(Integer, default=60)  # trần request mỗi đêm
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Lần gần nhất yêu cầu quét danh sách (lịch 03:00 hoặc "Quét ngay"): chốt idempotent/dedupe.
    list_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_list_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_list_status: Mapped[str | None] = mapped_column(String(16))
    last_list_error: Mapped[str | None] = mapped_column(Text)
    last_detail_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_detail_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketAreaHotel(Base):
    """Khách sạn từng thấy trong danh sách của khu vực. `best_rank`: vị trí tốt nhất ở ngày quét
    gần nhất (1 = đầu trang 1)."""

    __tablename__ = "market_area_hotels"
    __table_args__ = (Index("ix_market_area_hotels_hotel", "hotel_id"),)

    area_id: Mapped[int] = mapped_column(
        ForeignKey("market_areas.id", ondelete="CASCADE"), primary_key=True
    )
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    best_rank: Mapped[int | None] = mapped_column(Integer)


class MarketListScan(Base):
    """Một lượt quét khu vực cho một đêm: số liệu thị trường, danh sách (1 phòng, 2 người lớn) và
    thang phòng trống (N phòng, 1 người lớn/phòng)."""

    __tablename__ = "market_list_scans"
    __table_args__ = (
        Index("ix_market_list_scans_area_date", "area_id", "stay_date", "scanned_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("market_areas.id", ondelete="CASCADE"))
    stay_date: Mapped[date] = mapped_column(Date)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Số chỗ còn phòng TRONG khu vực khớp phân khúc (không tính phần Booking nới thêm).
    properties_found: Mapped[int | None] = mapped_column(Integer)
    pages: Mapped[int] = mapped_column(Integer, default=0)  # số request của đêm
    hotels_seen: Mapped[int] = mapped_column(Integer, default=0)
    priced: Mapped[int] = mapped_column(Integer, default=0)
    # running | completed | capped (chạm trần request) | blocked | error
    status: Mapped[str] = mapped_column(String(16), default="running")
    error: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(8))  # graphql | ssr (dự phòng)
    # Bộ lọc của truy vấn phân khúc lúc quét (phân khúc + bán kính): mẫu số phân khúc chỉ so các
    # lượt cùng phạm vi, đổi phân khúc/bán kính không lẫn số cũ.
    nflt: Mapped[str | None] = mapped_column(String(250))
    autoextended: Mapped[int | None] = mapped_column(Integer)  # chỗ Booking nới thêm ngoài khu vực
    low_availability: Mapped[bool | None] = mapped_column(Boolean)
    # Truy vấn "thị trường" (không lọc phân khúc): số còn phòng, % đã kín Booking tự tính (chỉ khi
    # truy vấn không có bộ lọc nào), facet (thành phần loại hình, hạng sao…).
    unavailability_pct: Mapped[int | None] = mapped_column(SmallInteger)
    market_available: Mapped[int | None] = mapped_column(Integer)
    market_facets: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    facets: Mapped[dict[str, int] | None] = mapped_column(JSONB)  # facet của truy vấn phân khúc
    price_histogram: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {min, max, bars}
    # Thang (N phòng, 1 người lớn/phòng): {"N": {"available", "autoextended", "class": {"3": n}}}.
    ladder: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Đã liệt kê id ở mọi nấc: `market_list_prices.rooms_min` của đêm này dùng được.
    enumerated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class MarketListPrice(Base):
    """Khách sạn thấy trong lượt quét một đêm: giá trên thẻ (VND, gồm thuế phí khi trang ghi rõ phần
    cộng thêm), hạng, và nấc phòng lớn nhất còn bán được."""

    __tablename__ = "market_list_prices"
    __table_args__ = (Index("ix_market_list_prices_hotel", "hotel_id"),)

    scan_id: Mapped[int] = mapped_column(
        ForeignKey("market_list_scans.id", ondelete="CASCADE"), primary_key=True
    )
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    rank: Mapped[int | None] = mapped_column(Integer)  # vị trí theo thứ tự "phổ biến"; None: lấp
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    # Vị trí hiển thị (roadmap 7.2): thẻ quảng cáo ("Ad") tách khỏi thứ hạng tự nhiên; huy hiệu
    # Preferred/Preferred Plus và tên deal trên thẻ.
    sponsored: Mapped[bool | None] = mapped_column(Boolean)
    badges: Mapped[list[str] | None] = mapped_column(JSONB)
    # Nấc lớn nhất khách sạn còn bán được (N phòng cùng lúc): 1 = có trong danh sách; ≥ 2 từ thang.
    rooms_min: Mapped[int | None] = mapped_column(SmallInteger)
    only_left: Mapped[int | None] = mapped_column(SmallInteger)  # "We have N left at this price"
