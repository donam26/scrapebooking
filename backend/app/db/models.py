from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
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
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    insight_language: Mapped[str] = mapped_column(String(8), default="vi")
    insight_hour: Mapped[str] = mapped_column(String(5), default="07:30")
    country_code: Mapped[str] = mapped_column(String(2), default="vn")
    # Kênh dùng cho heatmap/compset mặc định (D10).
    reference_channel: Mapped[str] = mapped_column(String(16), default="booking")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Hạn mức riêng (app/api/quotas.py): {"max_hotels": 25, "manual_scans_per_day": 6, …}.
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Hotel(Base):
    """Khách sạn (property). URL/định danh trên từng kênh nằm ở `listings`."""

    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2))
    star_rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    # Từ trang kết quả tìm kiếm của kênh (thị trường toàn thành phố, migration 0011).
    review_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    review_count: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Listing(Base):
    """Một khách sạn trên một kênh. Khoá nghiệp vụ (hotel_id, channel) dùng ở mọi bảng quan sát."""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("hotel_id", "channel", name="uq_listings_hotel_channel"),
        UniqueConstraint("channel", "listing_key", name="uq_listings_channel_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    channel: Mapped[str] = mapped_column(String(16))
    listing_key: Mapped[str] = mapped_column(String(300))
    external_id: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(300))
    # suggested (gợi ý chờ xác nhận) | rejected (người dùng bỏ gợi ý, không gợi ý lại) |
    # unverified | active | broken | paused
    status: Mapped[str] = mapped_column(String(16))
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Số lần probe/verify trả "không tồn tại" liên tiếp (qua session khác nhau). Đạt ngưỡng mới
    # đánh `broken`; một trang challenge trả 200 không giết listing. Về 0 khi có dữ liệu.
    not_found_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantHotel(Base):
    __tablename__ = "tenant_hotels"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # self | competitor
    label: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint(
            "hotel_id", "channel", "external_room_id", name="uq_room_types_listing_room"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    channel: Mapped[str] = mapped_column(String(16))
    external_room_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))
    max_occupancy: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_key: Mapped[str] = mapped_column(String(64), unique=True)
    channel: Mapped[str] = mapped_column(String(16))  # mỗi run thuộc một kênh (D9)
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
        Index("ix_probes_hotel_channel_date", "hotel_id", "channel", "stay_date", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    channel: Mapped[str] = mapped_column(String(16))
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
    channel: Mapped[str] = mapped_column(String(16))
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rooms_left: Mapped[int | None] = mapped_column(Integer)
    stock_confidence: Mapped[str] = mapped_column(String(16))
    stock_scope: Mapped[str] = mapped_column(String(16), default="room_type")
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
    channel: Mapped[str] = mapped_column(String(16))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # available | sold_out | unknown
    exact_rooms_left: Mapped[int | None] = mapped_column(Integer)
    room_types_available: Mapped[int] = mapped_column(Integer, default=0)
    room_types_sold_out: Mapped[int] = mapped_column(Integer, default=0)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_refundable_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))


class AvailabilityEvent(Base):
    __tablename__ = "availability_events"
    __table_args__ = (
        UniqueConstraint(
            "scan_run_id",
            "hotel_id",
            "room_type_id",
            "stay_date",
            "event_type",
            name="uq_availability_events_run_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_availability_events_hotel_observed", "hotel_id", "observed_at"),
        Index("ix_availability_events_stay_date", "stay_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    channel: Mapped[str] = mapped_column(String(16))
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
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    as_of_scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    days_to_arrival: Mapped[int] = mapped_column(Integer)
    pickup_24h: Mapped[int | None] = mapped_column(Integer)
    velocity_3d: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    sold_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_refundable_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    price_change_7d_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    availability_status: Mapped[str] = mapped_column(String(16))
    exact_rooms_left: Mapped[int | None] = mapped_column(Integer)
    exact_share: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Probe mới nhất không dùng được (blocked/error): giá và số phòng giữ từ lần dùng được cuối,
    # `stale_since` = lúc dữ liệu bắt đầu cũ. None khi lần quan sát mới nhất dùng được.
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # Tăng khi đổi mật khẩu/khoá/"đăng xuất mọi thiết bị": JWT mang `tv` cũ bị từ chối ngay.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """Nhật ký thao tác nhạy cảm (đăng nhập, đổi mật khẩu, tạo/khoá user, đổi cài đặt, sửa
    listing…). Chỉ ghi, không sửa; operator đọc qua DB/CLI."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_at", "tenant_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(48))
    target: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    ip: Mapped[str | None] = mapped_column(String(64))


class PasswordResetToken(Base):
    """Token đặt lại mật khẩu dùng một lần (lưu băm SHA-256, hết hạn sau ít phút)."""

    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmsColumnMapping(Base):
    __tablename__ = "pms_column_mappings"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(32), primary_key=True)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Thông báo email (đợt 1 sau nghiên cứu đối thủ)
# ---------------------------------------------------------------------------


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    __table_args__ = (
        Index(
            "uq_notification_recipients_tenant_email",
            "tenant_id",
            func.lower("email"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(254))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationRule(Base):
    """Một dòng mỗi (tenant, loại thông báo). Chưa có dòng = dùng mặc định của loại đó."""

    __tablename__ = "notification_rules"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """Outbox + nhật ký: chèn theo `dedupe_key` duy nhất trước khi gửi, chạy lại không gửi trùng."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # sending | sent | failed | skipped
    subject: Mapped[str] = mapped_column(String(300), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    recipients: Mapped[list[str]] = mapped_column(JSONB, default=list)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"))
    insight_id: Mapped[int | None] = mapped_column(ForeignKey("insights.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Đa kênh: tín hiệu cầu do kênh công bố (D5)
# ---------------------------------------------------------------------------


class ListingDemandSignal(Base):
    """ "Đặt 13 lần trong 24 giờ" (Agoda), "đã bán 2 phòng/24h" (ivivu)… Là thông điệp của kênh,
    luôn hiển thị kèm nguồn; không đưa vào chỉ số giá."""

    __tablename__ = "listing_demand_signals"
    __table_args__ = (
        Index("ix_listing_demand_signals_hotel_observed", "hotel_id", "channel", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    channel: Mapped[str] = mapped_column(String(16))
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"))
    stay_date: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(24))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    window_hours: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
