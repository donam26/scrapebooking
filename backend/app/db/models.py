from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    scan_times: Mapped[list[str]] = mapped_column(
        ARRAY(String(5)), default=lambda: ["06:00", "14:00", "22:00"]
    )
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    insight_language: Mapped[str] = mapped_column(String(8), default="vi")
    insight_hour: Mapped[str] = mapped_column(String(5), default="07:30")
    country_code: Mapped[str] = mapped_column(String(2), default="vn")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_url: Mapped[str] = mapped_column(Text)
    booking_slug: Mapped[str] = mapped_column(String(200), unique=True)
    booking_hotel_id: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2))
    star_rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TenantHotel(Base):
    __tablename__ = "tenant_hotels"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # self | competitor
    label: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("hotel_id", "booking_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    booking_room_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(300))
    max_occupancy: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_key: Mapped[str] = mapped_column(String(32), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    total_probes: Mapped[int] = mapped_column(Integer, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, default=0)
    sold_out_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Probe(Base):
    __tablename__ = "probes"
    __table_args__ = (
        UniqueConstraint("scan_run_id", "hotel_id", "stay_date"),
        Index("ix_probes_hotel_date_fetched", "hotel_id", "stay_date", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    checkin: Mapped[date] = mapped_column(Date)
    checkout: Mapped[date] = mapped_column(Date)
    nights: Mapped[int] = mapped_column(Integer)
    adults: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    method: Mapped[str | None] = mapped_column(String(16))
    proxy_country: Mapped[str | None] = mapped_column(String(2))
    session_id: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class HotelCalendar(Base):
    __tablename__ = "hotel_calendars"

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    available: Mapped[bool] = mapped_column(Boolean)
    min_length_of_stay: Mapped[int] = mapped_column(Integer, default=1)
    avg_price_display: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoomSnapshot(Base):
    __tablename__ = "room_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("id", "scanned_at"),
        Index("ix_room_snapshots_hotel_date_time", "hotel_id", "stay_date", "scanned_at"),
        {"postgresql_partition_by": "RANGE (scanned_at)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    probe_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("probes.id"))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rooms_left: Mapped[int | None] = mapped_column(Integer)
    stock_confidence: Mapped[str] = mapped_column(String(16))
    badge_count: Mapped[int | None] = mapped_column(Integer)
    dropdown_max: Mapped[int | None] = mapped_column(Integer)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_refundable_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    rates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class ScrapeSessionRow(Base):
    __tablename__ = "scrape_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    proxy_id: Mapped[str] = mapped_column(String(128))
    proxy_country: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")


# ---------------------------------------------------------------------------
# Giai đoạn 2: analytics
# ---------------------------------------------------------------------------


class HotelDateSnapshot(Base):
    __tablename__ = "hotel_date_snapshots"

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # available | sold_out | unknown
    exact_rooms_left: Mapped[int | None] = mapped_column(Integer)
    room_types_available: Mapped[int] = mapped_column(Integer, default=0)
    room_types_sold_out: Mapped[int] = mapped_column(Integer, default=0)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))


class AvailabilityEvent(Base):
    __tablename__ = "availability_events"
    __table_args__ = (
        UniqueConstraint(
            "scan_run_id", "hotel_id", "room_type_id", "stay_date", "event_type",
            name="uq_availability_events_run_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_availability_events_hotel_observed", "hotel_id", "observed_at"),
        Index("ix_availability_events_stay_date", "stay_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    room_type_id: Mapped[int | None] = mapped_column(ForeignKey("room_types.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[str] = mapped_column(String(24))
    from_value: Mapped[str | None] = mapped_column(String(64))
    to_value: Mapped[str | None] = mapped_column(String(64))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    confidence: Mapped[str] = mapped_column(String(16))
    previous_scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"))
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HotelDateMetric(Base):
    __tablename__ = "hotel_date_metrics"

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    as_of_scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    days_to_arrival: Mapped[int] = mapped_column(Integer)
    pickup_24h: Mapped[int | None] = mapped_column(Integer)
    velocity_3d: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    sold_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    price_change_7d_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    availability_status: Mapped[str] = mapped_column(String(16))
    exact_rooms_left: Mapped[int | None] = mapped_column(Integer)
    exact_share: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Giai đoạn 2: người dùng và API
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # operator | tenant_admin | viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Giai đoạn 3: insight
# ---------------------------------------------------------------------------


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (Index("ix_insights_tenant_generated", "tenant_id", "generated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(String(16))  # daily | on_demand
    status: Mapped[str] = mapped_column(String(16), default="completed")
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(16))
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dropped_highlights: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    error: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[str | None] = mapped_column(String(128))


# ---------------------------------------------------------------------------
# Giai đoạn 4: PMS
# ---------------------------------------------------------------------------


class OwnHotelDaily(Base):
    __tablename__ = "own_hotel_daily"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rooms_total: Mapped[int | None] = mapped_column(Integer)
    rooms_sold: Mapped[int | None] = mapped_column(Integer)
    rooms_available: Mapped[int | None] = mapped_column(Integer)
    occupancy_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    adr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    source: Mapped[str] = mapped_column(String(16))  # csv | api
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PmsImport(Base):
    __tablename__ = "pms_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"))
    filename: Mapped[str] = mapped_column(String(255))
    adapter: Mapped[str] = mapped_column(String(32))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16))  # completed | failed | partial
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PmsColumnMapping(Base):
    __tablename__ = "pms_column_mappings"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(32), primary_key=True)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
