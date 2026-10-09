from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

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
    active: bool
    created_at: datetime
    source_markets: list[str] = []


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

    _language = field_validator("insight_language")(_check_language)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    scan_times: list[str] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=90)
    insight_language: str | None = None
    insight_hour: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    active: bool | None = None
    # Thị trường nguồn khách theo dõi lịch nghỉ (roadmap 7.5): cn, kr, jp, tw, ru, in, us, au.
    source_markets: list[str] | None = None

    _language = field_validator("insight_language")(_check_language)

    @field_validator("source_markets")
    @classmethod
    def _markets(cls, v: list[str] | None) -> list[str] | None:
        from app.holidays.data import SOURCE_MARKETS

        if v is None:
            return v
        out = sorted({m.strip().lower() for m in v if m.strip()})
        bad = [m for m in out if m not in SOURCE_MARKETS]
        if bad:
            raise ValueError(f"unknown source markets: {', '.join(bad)}")
        return out


# ---- kênh & listing ----


class ChannelOut(BaseModel):
    code: str
    name: str
    example_url: str
    hosts: list[str]  # tên miền gốc: ["booking.com"]
    collectable: bool


class ListingOut(ORM):
    id: int
    hotel_id: int
    channel: str
    listing_key: str
    url: str
    external_id: str | None
    name: str | None
    # unverified (đang kiểm tra) | active | broken | paused
    status: str
    match_score: Decimal | None
    last_error: str | None
    verified_at: datetime | None


class ListingCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ListingAction(BaseModel):
    # pause/resume: ngừng/quét lại; retry: kiểm tra lại listing hỏng
    action: str = Field(pattern="^(pause|resume|retry)$")


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
    # Tổng số phòng công bố/người dùng nhập (5.6); điểm và số review mới nhất (trang kết quả).
    rooms_total: int | None = None
    review_score: Decimal | None = None
    review_count: int | None = None


class WatchItemOut(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    active: bool
    added_at: datetime
    # Compset theo khách sạn của bạn (5.5): null = dùng chung; chính/phụ (7.3).
    compset_of: int | None = None
    tier: Literal["primary", "secondary"] = "primary"
    weight: Decimal = Decimal(1)


class WatchItemCreate(BaseModel):
    # Đường dẫn trang khách sạn trên Booking.com.
    url: str = Field(min_length=8, max_length=2000)
    role: str = Field(default="competitor", pattern="^(self|competitor)$")
    label: str | None = Field(default=None, max_length=120)


class WatchItemUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(self|competitor)$")
    label: str | None = Field(default=None, max_length=120)
    active: bool | None = None
    compset_of: int | None = None
    tier: Literal["primary", "secondary"] | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=10)
    # Tổng số phòng của khách sạn (công bố trên website/OTA, hoặc số thật với khách sạn của bạn).
    rooms_total: int | None = Field(default=None, ge=1, le=5000)


class CompsetReviewOut(BaseModel):
    """Rà soát compset theo quy tắc CoStar STR (7.3): ≥4 đối thủ, ≥3 không cùng chủ (chưa kiểm
    được), không khách sạn nào quá 50% số phòng compset; nhắc rà soát ≥2 lần/năm."""

    own_hotel_id: int | None
    primary: int
    secondary: int
    rooms_known: int
    warnings: list[str]  # mã: too_few | dominant_hotel | rooms_unknown | review_due
    dominant_hotel_id: int | None = None
    dominant_share: Decimal | None = None
    last_change_at: datetime | None = None


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
    # Năm trạng thái (roadmap 2.7): available | sold_out | restricted | no_price | error | null.
    state: str | None = None
    # Số đêm tối thiểu kênh yêu cầu (>1 = đêm bị hạn chế số đêm, giá không so với giá 1 đêm).
    min_stay: int | None = None
    # Nhãn khuyến mãi đang chạy trên các gói công khai → độ sâu % (so giá gạch) hoặc null.
    promos: dict[str, str | None] | None = None
    # Quan sát cũ hơn 48 giờ: không vào trung vị compset (1.13).
    stale: bool = False


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
    # Vị trí giá của bạn (1 = rẻ nhất) trong `priced_hotels` khách sạn có giá đêm đó (gồm bạn).
    own_rank: int | None
    priced_hotels: int
    # Cỡ mẫu (1.9): n đối thủ có giá cùng điều kiện / N đối thủ compset chính. sample: ok (≥4),
    # small (3, hiện mờ), insufficient (<3: không tính trung vị/chỉ số/vị trí).
    competitors_total: int = 0
    competitors_priced: int = 0
    competitors_restricted: int = 0
    competitors_low: int = 0
    competitors_stale: int = 0
    sample: Literal["ok", "small", "insufficient"] = "insufficient"
    own_hotel_id: int | None = None
    own_min_stay: int | None = None


class HolidayOut(BaseModel):
    date: date
    name: str  # theo ngôn ngữ request
    # Mã ổn định cho giao diện (không dò theo tên): `kind` để tô màu, `group` gộp ngày cùng đợt.
    kind: HolidayKind
    group: str


class DataStatusOut(BaseModel):
    """Độ tin cậy dữ liệu Booking.com của tenant (roadmap 0.6, 0.7)."""

    now: datetime
    stale_after_hours: int
    # Quan sát có dữ liệu gần nhất (không phải lượt quét kết thúc gần nhất).
    last_data_at: datetime | None
    # % lượt đọc trang thành công 7 ngày (ok, hết phòng, không có phòng 1 đêm / tổng có request).
    success_rate_7d: Decimal | None = None
    probes_7d: int = 0
    failed_7d: int = 0
    # Không có dữ liệu mới quá một chu kỳ quét (`stale_after_hours`).
    stale: bool = False


class OverviewOut(BaseModel):
    start: date
    end: date
    channel: str  # luôn "booking"
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


class RateDetailOut(BaseModel):
    """Giá và tình trạng Booking.com của (khách sạn, đêm) ở lần quét gần nhất."""

    availability_status: str | None
    exact_rooms_left: int | None
    min_price: Decimal | None
    min_refundable_price: Decimal | None
    currency: str | None
    last_observed_at: datetime | None
    min_breakfast_price: Decimal | None = None
    min_room_only_price: Decimal | None = None
    min_stay: int | None = None
    # Gói rẻ nhất: nhãn KM, giá trước KM (giá gạch), khoá gói "hoàn huỷ|bữa sáng".
    cheapest_rate: dict[str, Any] | None = None
    prices_by_key: dict[str, str] | None = None


class DayDetailOut(BaseModel):
    hotel: HotelOut
    label: str | None = None  # nhãn tenant đặt cho khách sạn
    stay_date: date
    channel: str  # luôn "booking"
    rate: RateDetailOut | None = None
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
    # Lý do: lowest_rate_shift (cheapest_gone, cheapest_back, rate_gone, rate_back, mix); khoá gói
    # "hoàn huỷ|bữa sáng" của đổi giá.
    reason: str | None = None
    detail: dict[str, Any] | None = None


class HotelDetailOut(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    channel: str
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
    # Zalo ZNS đã cấu hình (OA xác thực + template duyệt) chưa (3.3).
    zalo_configured: bool = False
    channels: list[str] = ["email", "zalo", "webhook"]


NotifyChannel = Literal["email", "zalo", "webhook"]
SUBSCRIPTION_KINDS = ("alerts", "daily_insight", "weekly_report", "data_stale")
_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class SubscriptionIn(BaseModel):
    """Đăng ký nhận tin của một người (3.4). kinds rỗng = mọi loại tin."""

    channel: NotifyChannel
    target: str = Field(min_length=3, max_length=500)
    kinds: list[Literal["alerts", "daily_insight", "weekly_report", "data_stale"]] = []
    quiet_start: str | None = Field(default=None, pattern=_HHMM)
    quiet_end: str | None = Field(default=None, pattern=_HHMM)
    max_per_day: int | None = Field(default=None, ge=1, le=50)
    active: bool = True


class SubscriptionOut(SubscriptionIn):
    id: int
    user_id: int | None
    created_at: datetime


class EngagementWeekOut(BaseModel):
    week: str  # "2026-W41"
    channel: str
    sent: int
    failed: int
    skipped: int
    clicked: int
    resolved: int
    cost_vnd: Decimal


class EngagementOut(BaseModel):
    """Đo O4: tin tới đúng chỗ và có hành động (lượt nhấn, "Đã xử lý") theo tuần, theo kênh."""

    weeks: list[EngagementWeekOut]


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
    channel: str = "email"
    resolved_at: datetime | None = None


OverviewOut.model_rebuild()
DayDetailOut.model_rebuild()
