from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Ho_Chi_Minh"
    scan_times: list[str] = ["06:00", "14:00", "22:00"]
    horizon_days: int = Field(default=30, ge=1, le=90)
    insight_language: str = "vi"
    insight_hour: str = "07:30"
    country_code: str = Field(default="vn", min_length=2, max_length=2)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    scan_times: list[str] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=90)
    insight_language: str | None = None
    insight_hour: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    active: bool | None = None


# ---- watchlist ----


class HotelOut(ORM):
    id: int
    booking_url: str
    booking_slug: str
    booking_hotel_id: str | None
    name: str | None
    city: str | None
    country_code: str
    star_rating: Decimal | None


class WatchItemOut(BaseModel):
    hotel: HotelOut
    role: str
    label: str | None
    active: bool
    added_at: datetime


class WatchItemCreate(BaseModel):
    booking_url: str
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


class OverviewOut(BaseModel):
    start: date
    end: date
    hotels: list[HotelRow]
    compset: list[CompsetDayOut]
    last_run: "ScanRunOut | None"


class RoomTypeOut(ORM):
    id: int
    booking_room_id: str
    name: str
    max_occupancy: int | None


class RoomSnapshotOut(ORM):
    id: int
    room_type_id: int
    stay_date: date
    scanned_at: datetime
    rooms_left: int | None
    stock_confidence: str
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


class DayDetailOut(BaseModel):
    hotel: HotelOut
    stay_date: date
    room_types: list[RoomTypeOut]
    latest: list[RoomSnapshotOut]
    history: list[RoomSnapshotOut]
    observations: list[HotelDateSnapshotOut]
    events: list["EventOut"]


class EventOut(BaseModel):
    id: int
    hotel_id: int
    hotel_name: str | None
    hotel_slug: str
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
    metrics: list[DateCell]
    events: list[EventOut]


class ScanRunOut(ORM):
    id: int
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


OverviewOut.model_rebuild()
DayDetailOut.model_rebuild()
