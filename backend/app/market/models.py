"""Bảng của module thị trường (đợt 2). Tách khỏi `app/db/models.py` để không đụng file đang được
refactor; dùng chung `Base` nên Alembic và test vẫn thấy."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class OccupancyEstimate(Base):
    """Công suất ước tính của (khách sạn, kênh, đêm) ở một lượt quét (app/market/occupancy.py)."""

    __tablename__ = "occupancy_estimates"
    __table_args__ = (
        Index(
            "ix_occupancy_estimates_hotel_date_time",
            "hotel_id",
            "channel",
            "stay_date",
            "scanned_at",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    days_to_arrival: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # available | sold_out
    inventory: Mapped[int] = mapped_column(Integer)
    left_low: Mapped[int] = mapped_column(Integer)
    left_high: Mapped[int] = mapped_column(Integer)
    occ_low: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    occ_high: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    coverage: Mapped[Decimal] = mapped_column(Numeric(5, 4))


class OccupancyEstimateRun(Base):
    """Lượt quét đã được ước tính (kể cả khi không ra dòng nào), để cron không xử lý lại."""

    __tablename__ = "occupancy_estimate_runs"

    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    estimated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PriceSuggestionDecision(Base):
    """Khách sạn đã xử lý gợi ý giá một đêm: "applied" (đã áp dụng) hoặc "dismissed" (bỏ qua)."""

    __tablename__ = "price_suggestion_decisions"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # raise | hold | lower
    decision: Mapped[str] = mapped_column(String(16))
    change_pct: Mapped[int] = mapped_column(Integer)
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # RMS-lite (Phase 6): khách sạn, giá mục tiêu gợi ý, giá đã áp dụng, lý do lúc quyết định.
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    applied_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reasons: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class LocalEvent(Base):
    """Sự kiện địa phương tenant tự nhập (lễ hội, hội nghị/MICE, thể thao, mùa…) cho lịch Terminal+.

    `expected_uplift_pct` là mức tăng cầu người dùng dự kiến (không phải số đo được).
    """

    __tablename__ = "local_events"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_local_events_range"),
        Index("ix_local_events_tenant_start", "tenant_id", "start_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(16))  # festival | mice | sports | season | other
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    expected_uplift_pct: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OtbSnapshot(Base):
    """Phòng đã đặt (on the books) của khách sạn của bạn tính đến ngày `as_of_date` cho đêm
    `stay_date` (roadmap 5.1). Mỗi ngày nhập một bản chụp, không ghi đè bản của ngày khác: từ đó có
    pickup (OTB đổi giữa hai ngày), pace (so cùng số ngày trước khi đến) và STLY."""

    __tablename__ = "otb_snapshots"
    __table_args__ = (
        Index("ix_otb_snapshots_hotel_stay", "tenant_id", "hotel_id", "stay_date", "as_of_date"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rooms_otb: Mapped[int] = mapped_column(Integer)
    revenue_otb: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    rooms_available: Mapped[int | None] = mapped_column(Integer)  # phòng sẵn có (trừ phòng hỏng)
    cancellations: Mapped[int | None] = mapped_column(Integer)
    group_rooms: Mapped[int | None] = mapped_column(Integer)  # phòng của khối đoàn trong OTB
    source: Mapped[str] = mapped_column(String(16))  # otb_report | bookings
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PriceStrategy(Base):
    """Chiến lược giá của một khách sạn của bạn (roadmap 6.1): giá gốc, sàn/trần, định vị mục tiêu
    so compset, làm tròn, mức đổi tối đa mỗi ngày, điều chỉnh theo thứ/lễ/sát ngày."""

    __tablename__ = "price_strategies"

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    floor_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    ceiling_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Chỉ số giá niêm yết mục tiêu: 100 = ngang trung vị compset, 105 = cao hơn 5%.
    target_index: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=100, server_default="100")
    round_to: Mapped[int] = mapped_column(Integer, default=10000, server_default="10000")
    max_daily_change_pct: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    # Điều chỉnh % theo thứ của đêm (0 = thứ Hai … 6 = Chủ nhật), VD {"4": 5, "5": 10}.
    weekday_adj: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    holiday_uplift_pct: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    last_minute_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    last_minute_adj_pct: Mapped[int] = mapped_column(Integer, default=-5, server_default="-5")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class HotelReviewSnapshot(Base):
    """Điểm và số review theo ngày (roadmap 7.1, N4) từ thẻ trang kết quả tìm kiếm: tốc độ
    review/tháng, khoảng cách tới mốc 7,0 / 7,5 / 8,0 / 9,0 của Booking."""

    __tablename__ = "hotel_review_snapshots"

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    observed_on: Mapped[date] = mapped_column(Date, primary_key=True)
    review_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    review_count: Mapped[int | None] = mapped_column(Integer)
    # Huy hiệu trên thẻ (7.2): preferred, preferred_plus, ad, deal tên chiến dịch…
    badges: Mapped[list[str] | None] = mapped_column(JSONB)
    preferred: Mapped[bool | None] = mapped_column(Boolean)
