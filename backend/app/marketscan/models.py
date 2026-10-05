"""Bảng thị trường toàn thành phố (migration 0011). Dùng chung `Base` nên Alembic và test vẫn thấy.

Khu vực thuộc một tenant; khách sạn (`hotels`) dùng chung toàn hệ thống như mọi nơi khác. Khách sạn
thị trường chỉ hiện ở tổng quan/compset của tenant khi tenant tự thêm vào watchlist.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class MarketArea(Base):
    """Thành phố/quận trên một kênh (dest_id/dest_type của Booking) mà tenant theo dõi cả chợ."""

    __tablename__ = "market_areas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "channel", "dest_type", "dest_id", name="uq_market_areas_dest"
        ),
        CheckConstraint("detail_horizon_days BETWEEN 1 AND 90", name="ck_market_areas_horizon"),
        CheckConstraint("list_nights BETWEEN 1 AND 30", name="ck_market_areas_list_nights"),
        CheckConstraint("detail_max_hotels >= 0", name="ck_market_areas_max_hotels"),
        CheckConstraint("max_pages BETWEEN 1 AND 100", name="ck_market_areas_max_pages"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16), default="booking")
    name: Mapped[str] = mapped_column(String(200))
    dest_id: Mapped[str] = mapped_column(String(32))
    dest_type: Mapped[str] = mapped_column(String(16))  # city | district | region
    country_code: Mapped[str] = mapped_column(String(2), default="vn")
    list_nights: Mapped[int] = mapped_column(Integer, default=14)
    detail_horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    detail_max_hotels: Mapped[int] = mapped_column(Integer, default=300)
    max_pages: Mapped[int] = mapped_column(Integer, default=60)  # trần số trang mỗi đêm
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
    """Một lượt lật trang danh sách của khu vực cho một đêm (1 đêm, 2 người lớn)."""

    __tablename__ = "market_list_scans"
    __table_args__ = (
        Index("ix_market_list_scans_area_date", "area_id", "stay_date", "scanned_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("market_areas.id", ondelete="CASCADE"))
    stay_date: Mapped[date] = mapped_column(Date)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    properties_found: Mapped[int | None] = mapped_column(Integer)  # "N properties found" của kênh
    pages: Mapped[int] = mapped_column(Integer, default=0)
    hotels_seen: Mapped[int] = mapped_column(Integer, default=0)
    priced: Mapped[int] = mapped_column(Integer, default=0)
    # running | completed (hết danh sách) | capped (chạm trần trang) | blocked | error
    status: Mapped[str] = mapped_column(String(16), default="running")
    error: Mapped[str | None] = mapped_column(Text)


class MarketListPrice(Base):
    """Giá hiển thị trên thẻ kết quả (VND, gồm thuế phí khi trang ghi rõ phần cộng thêm)."""

    __tablename__ = "market_list_prices"
    __table_args__ = (Index("ix_market_list_prices_hotel", "hotel_id"),)

    scan_id: Mapped[int] = mapped_column(
        ForeignKey("market_list_scans.id", ondelete="CASCADE"), primary_key=True
    )
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
