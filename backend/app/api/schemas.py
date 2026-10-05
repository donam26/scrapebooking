from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.holidays.data import HolidayKind
from app.i18n import LOCALES


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(ORM):
    id: int
    email: str
    role: str
    tenant_id: int | None
    active: bool


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(operator|tenant_admin|viewer)$")
    tenant_id: int | None = None


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(operator|tenant_admin|viewer)$")
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=200)
    password: str = Field(min_length=8, max_length=200)


# ---- tenants ----


class TenantOut(ORM):
    id: int
    name: str
    timezone: str
    scan_times: list[str]
    horizon_days: int
    insight_language: str
    insight_hour: str
    country_code: str
    reference_channel: str
    active: bool
    # Hạn mức riêng do operator đặt (rỗng = mặc định hệ thống): max_hotels, manual_scans_per_day,
    # insights_per_day.
    limits: dict[str, int] = {}
    created_at: datetime


def _check_language(value: str | None) -> str | None:
    """Ngôn ngữ báo cáo (bản tin AI, báo cáo tuần, mọi email) phải có catalog ở backend."""
    if value is not None and value not in LOCALES:
        raise ValueError(f"insight_language must be one of {', '.join(LOCALES)}")
    return value


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Ho_Chi_Minh"
    scan_times: list[str] = ["06:00", "14:00", "22:00"]
    horizon_days: int = Field(default=90, ge=1, le=90)
    insight_language: str = "vi"
    insight_hour: str = "07:30"
    country_code: str = Field(default="vn", min_length=2, max_length=2)
    reference_channel: str = "booking"

    _language = field_validator("insight_language")(_check_language)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    scan_times: list[str] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=90)
    insight_language: str | None = None
    insight_hour: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    reference_channel: str | None = None
    active: bool | None = None
    limits: dict[str, int] | None = None  # chỉ operator (PATCH /tenants/{id})

    _language = field_validator("insight_language")(_check_language)


# ---- kênh & listing ----


class ChannelOut(BaseModel):
    code: str
    name: str
    example_url: str
    hosts: list[str]  # tên miền gốc, VD ["trip.com"]
    collectable: bool  # đã quét được (có collector); False: nhận diện URL nhưng chưa hỗ trợ


class ListingOut(ORM):
    id: int
    hotel_id: int
    channel: str
    listing_key: str
    url: str
    external_id: str | None
    name: str | None
    # suggested (chờ xác nhận) | unverified (đang kiểm tra) | active | broken | paused
    status: str
    match_score: Decimal | None
    last_error: str | None
    verified_at: datetime | None


class ListingCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ListingAction(BaseModel):
    # confirm: nhận gợi ý; reject: bỏ gợi ý; pause/resume: ngừng/quét lại; retry: kiểm tra lại
    action: str = Field(pattern="^(confirm|reject|pause|resume|retry)$")


class DemandSignalOut(ORM):
    channel: str
    kind: str
    value: Decimal
    window_hours: int | None
    stay_date: date | None
    raw_text: str | None
    observed_at: datetime


# ---- watchlist ----


class HotelOut(BaseModel):
    id: int
    name: str | None
    city: str | None
    country_code: str
    star_rating: Decimal | None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    listings: list[ListingOut] = []


class WatchItemOut(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    active: bool
    added_at: datetime


class WatchItemCreate(BaseModel):
    # Đường dẫn trang khách sạn trên bất kỳ kênh được hỗ trợ (Booking, Agoda, ivivu, Trip.com…).
    url: str = Field(min_length=8, max_length=2000)
    role: str = Field(default="competitor", pattern="^(self|competitor)$")
    label: str | None = Field(default=None, max_length=120)


class WatchItemUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(self|competitor)$")
    label: str | None = Field(default=None, max_length=120)
    active: bool | None = None


# ---- data ----


class DateCell(BaseModel):
    stay_date: date
    availability_status: str | None
    exact_rooms_left: int | None
    min_price: Decimal | None
    currency: str | None
    pickup_24h: int | None
    velocity_3d: Decimal | None
    price_change_7d_pct: Decimal | None
    exact_share: Decimal | None
    sold_out_at: datetime | None
    restocked_at: datetime | None
    last_observed_at: datetime | None
    days_to_arrival: int | None
    # Probe mới nhất không dùng được: giá/số phòng giữ từ lần dùng được cuối, cũ từ mốc này.
    stale_since: datetime | None = None


class HotelRow(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    cells: list[DateCell]


class CompsetDayOut(BaseModel):
    stay_date: date
    competitors_observed: int
    competitors_sold_out: int
    sold_out_share: Decimal | None
    min_price: Decimal | None
    median_price: Decimal | None
    currency: str | None
    own_min_price: Decimal | None
    own_status: str | None
    own_occupancy_pct: Decimal | None
    own_rooms_available: int | None
    price_index: Decimal | None
    # Hạng giá của bạn (1 = rẻ nhất) trong `priced_hotels` khách sạn có giá đêm đó (gồm bạn).
    own_rank: int | None
    priced_hotels: int


class HolidayOut(BaseModel):
    date: date
    name: str  # theo ngôn ngữ request
    # Mã ổn định cho giao diện (không dò theo tên): `kind` để tô màu, `group` gộp ngày cùng đợt.
    kind: HolidayKind
    group: str


class OverviewOut(BaseModel):
    start: date
    end: date
    # Kênh của ô heatmap/compset (D10): mặc định kênh tham chiếu của tenant.
    channel: str
    # Kênh có listing đang quét trong watchlist của tenant (để chọn).
    channels: list[str]
    # Đêm xa nhất trong phạm vi quét của tenant (hôm nay + horizon - 1): đêm sau mốc này chưa
    # được quét nên ô trống là "ngoài phạm vi", không phải thiếu dữ liệu.
    horizon_end: date
    hotels: list[HotelRow]
    compset: list[CompsetDayOut]
    # Ngày lễ theo nước của tenant trong khoảng đang xem.
    holidays: list[HolidayOut]
    last_run: "ScanRunOut | None"


class RoomTypeOut(ORM):
    id: int
    channel: str
    external_room_id: str
    name: str
    max_occupancy: int | None


class RoomSnapshotOut(ORM):
    id: int
    channel: str
    room_type_id: int
    stay_date: date
    scanned_at: datetime
    rooms_left: int | None
    stock_confidence: str
    stock_scope: str
    badge_count: int | None
    dropdown_max: int | None
    min_price: Decimal | None
    min_refundable_price: Decimal | None
    currency: str | None
    rates: list[dict[str, Any]]


class HotelDateSnapshotOut(ORM):
    scan_run_id: int
    scanned_at: datetime
    status: str
    exact_rooms_left: int | None
    room_types_available: int
    room_types_sold_out: int
    min_price: Decimal | None
    currency: str | None


class ChannelDayOut(BaseModel):
    """Một kênh cho (khách sạn, đêm): đặt các kênh cạnh nhau (D4: không cộng số phòng)."""

    channel: str
    availability_status: str | None
    exact_rooms_left: int | None
    min_price: Decimal | None
    min_refundable_price: Decimal | None
    currency: str | None
    last_observed_at: datetime | None
    # Giá kênh này đã gồm thuế phí, theo phòng/đêm (D3): chỉ so rẻ/đắt giữa các kênh có cờ này.
    tax_inclusive: bool


class DayDetailOut(BaseModel):
    hotel: HotelOut
    label: str | None = None  # nhãn tenant đặt cho khách sạn
    stay_date: date
    channel: str  # kênh của phần chi tiết loại phòng/lịch sử
    channels: list[ChannelDayOut] = []
    demand_signals: list[DemandSignalOut] = []
    room_types: list[RoomTypeOut]
    # Lần quét gần nhất của ngày: trạng thái (available | sold_out | unknown) và thời điểm.
    # `latest` chỉ gồm loại phòng của đúng lần quét đó (rỗng khi hết phòng/không rõ).
    latest_status: str | None = None
    latest_scanned_at: datetime | None = None
    latest: list[RoomSnapshotOut]
    # Phạm vi quét, để giải thích khi đêm chưa có dữ liệu: tenant quét `horizon_days` đêm tính từ
    # hôm nay theo giờ địa phương (tới hết `horizon_end`); lượt quét gần nhất của khách sạn
    # (`last_scan_at`, xét mọi đêm) phủ tới đêm `last_scan_through`.
    horizon_days: int
    horizon_end: date
    last_scan_at: datetime | None = None
    last_scan_through: date | None = None
    history: list[RoomSnapshotOut]
    observations: list[HotelDateSnapshotOut]
    events: list["EventOut"]
    # Thị trường của tenant đêm này (để giải thích đêm ở đầu trang) và tên ngày lễ nếu có.
    compset: CompsetDayOut | None = None
    holiday: str | None = None
    holiday_kind: HolidayKind | None = None


class EventOut(BaseModel):
    id: int
    hotel_id: int
    hotel_name: str | None
    channel: str
    room_type_id: int | None
    room_type_name: str | None
    stay_date: date
    event_type: str
    from_value: str | None
    to_value: str | None
    delta: Decimal | None
    confidence: str
    previous_scan_run_id: int | None
    scan_run_id: int
    observed_at: datetime


class HotelDetailOut(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    channel: str
    demand_signals: list[DemandSignalOut] = []
    horizon_end: date  # như OverviewOut.horizon_end
    metrics: list[DateCell]
    events: list[EventOut]


class ScanRunOut(ORM):
    id: int
    channel: str
    trigger_key: str
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: str
    total_jobs: int
    total_probes: int
    ok_count: int
    sold_out_count: int
    blocked_count: int
    error_count: int


# ---- insights ----


class InsightOut(ORM):
    id: int
    tenant_id: int
    period_start: date
    period_end: date
    generated_at: datetime
    trigger: str
    status: str
    scan_run_id: int | None
    model: str
    prompt_version: str
    output_json: dict[str, Any] | None
    dropped_highlights: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    error: str | None


class InsightDetailOut(InsightOut):
    input_json: dict[str, Any]


# ---- health ----


class ScrapeSessionOut(ORM):
    id: str
    worker_id: str
    proxy_id: str
    proxy_country: str
    created_at: datetime
    expires_at: datetime
    retired_at: datetime | None
    request_count: int
    block_count: int
    status: str


class HealthSummaryOut(BaseModel):
    probes_15m: int
    blocked_15m: int
    block_rate_15m: float
    last_run: ScanRunOut | None
    active_sessions: int
    pending_analytics_runs: list[int]
    grafana_url: str | None


# ---- Thông báo email ----


class RecipientOut(ORM):
    id: int
    email: str
    active: bool
    created_at: datetime


class RecipientCreate(BaseModel):
    email: EmailStr


class NotificationRuleOut(BaseModel):
    kind: str
    active: bool
    params: dict[str, int]


class NotificationRuleUpdate(BaseModel):
    active: bool
    params: dict[str, int] = Field(default_factory=dict)


class NotificationSettingsOut(BaseModel):
    # Máy chủ email đã cấu hình chưa (chưa thì mọi thông báo chỉ ghi nhật ký, không gửi).
    email_configured: bool
    recipients: list[RecipientOut]
    rules: list[NotificationRuleOut]


class NotificationLogOut(BaseModel):
    id: int
    kind: str  # alerts | daily_insight | weekly_report | test
    status: str  # pending | sent | failed | skipped
    subject: str
    item_count: int
    recipients: list[str]
    # Lý do không gửi, dạng mã: no_recipients | smtp_not_configured | send_failed
    reason: str | None
    # Chi tiết kỹ thuật (lỗi SMTP): chỉ operator thấy.
    detail: str | None
    created_at: datetime
    sent_at: datetime | None


OverviewOut.model_rebuild()
DayDetailOut.model_rebuild()
