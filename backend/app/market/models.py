"""Bảng của module thị trường (đợt 2). Tách khỏi `app/db/models.py` để không đụng file đang được
refactor đa kênh; dùng chung `Base` nên Alembic và test vẫn thấy."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
