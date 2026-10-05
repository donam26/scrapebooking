from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class StockConfidence(StrEnum):
    EXACT = "exact"
    CAPPED = "capped"
    HIDDEN = "hidden"
    SOLD_OUT = "sold_out"


class ProbeStatus(StrEnum):
    OK = "ok"
    SOLD_OUT = "sold_out"
    NO_ROOMS_1N = "no_rooms_1n"
    BLOCKED = "blocked"
    ERROR = "error"
    SKIPPED_CALENDAR = "skipped_calendar"


class ProbeMethod(StrEnum):
    HTTP = "http"
    BROWSER = "browser"
    CALENDAR = "calendar"
    API = "api"  # API JSON của kênh


class StockScope(StrEnum):
    ROOM_TYPE = "room_type"  # "We have 2 left" của Booking: cả loại phòng
    RATE = "rate"  # "Chỉ còn 1 phòng có giá này" (Trip.com): chỉ mức giá đó
    PROPERTY = "property"  # cả khách sạn trên kênh


class DemandKind(StrEnum):
    """Tín hiệu cầu do kênh tự công bố (D5). Là thông điệp marketing: luôn ghi nguồn."""

    BOOKINGS_24H = "bookings_24h"  # Agoda "đặt 13 lần trong 24 giờ qua"
    BOOKINGS_TODAY = "bookings_today"  # Agoda "Đã được đặt N lần hôm nay"
    ROOMS_SOLD_24H = "rooms_sold_24h"  # ivivu "Đã bán 2 phòng trong 24 giờ qua"
    BOOKINGS_MONTH = "bookings_month"  # ivivu bookingInMonth
    LAST_BOOKED_MINUTES = "last_booked_minutes"  # Trip.com "Lần đặt gần nhất cách đây N phút"
    URGENCY_SCORE = "urgency_score"  # Agoda urgencyScore
    HIGH_DEMAND = "high_demand"  # kênh gắn cờ ngày nhu cầu cao


class PageOutcome(StrEnum):
    ROOMS = "rooms"  # có bảng phòng với ít nhất 1 dòng
    SOLD_OUT = "sold_out"  # có thông báo hết phòng rõ ràng
    EMPTY = "empty"  # không có bảng phòng, không có thông báo: nghi bị chặn hoặc min stay


@dataclass(frozen=True)
class ListingRef:
    """Một khách sạn trên một kênh (listing). Khoá = (hotel_id, channel)."""

    hotel_id: int
    channel: str
    listing_key: str  # khoá ổn định theo kênh, VD booking "vn/the-reverie-saigon"
    url: str  # trang khách sạn chuẩn hoá, không kèm ngày
    country_code: str
    external_id: str | None = None  # id của kênh (b_hotel_id, propertyId Agoda, hotelId ivivu…)

    @property
    def id(self) -> int:
        return self.hotel_id


@dataclass(frozen=True)
class RatePlan:
    name: str
    price: Decimal
    currency: str
    refundable: bool | None
    breakfast: bool | None
    max_persons: int | None = None  # "Max persons" của dòng giá (Booking có dòng riêng cho 1 khách)
    # Chuẩn giá D3: `price` = giá khách thấy (VND, /phòng/đêm, sau KM kênh tự áp).
    price_original: Decimal | None = None  # trước KM của kênh (giá gạch), None nếu kênh không có
    taxes_included: bool | None = None  # None = không chắc, không đem so giữa kênh
    promo_label: str | None = None  # "NOON FLASH", coupon tự áp…
    source_supplier: str | None = None  # nguồn bán lại (ivivu: IVIVU/AGODA/HBED…)


@dataclass(frozen=True)
class RoomOffer:
    external_room_id: str
    name: str
    max_occupancy: int | None
    badge_count: int | None
    dropdown_max: int | None
    rates: tuple[RatePlan, ...] = field(default_factory=tuple)
    # Phạm vi của tín hiệu tồn phòng (D4): room_type | rate | property.
    stock_scope: str = "room_type"

    @property
    def min_price(self) -> Decimal | None:
        return min((r.price for r in self.rates), default=None)

    @property
    def min_refundable_price(self) -> Decimal | None:
        return min((r.price for r in self.rates if r.refundable), default=None)

    @property
    def currency(self) -> str | None:
        return self.rates[0].currency if self.rates else None


@dataclass(frozen=True)
class ParsedPage:
    outcome: PageOutcome
    external_id: str | None
    hotel_name: str | None
    csrf_token: str | None
    offers: tuple[RoomOffer, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    method: ProbeMethod
    checkin: date
    checkout: date
    nights: int
    adults: int
    offers: tuple[RoomOffer, ...]
    raw_html: str | None
    http_status: int | None
    session_id: str | None
    duration_ms: int
    error: str | None = None
    external_id: str | None = None
    hotel_name: str | None = None
    demand_signals: tuple["DemandSignal", ...] = ()


@dataclass(frozen=True)
class CalendarDay:
    checkin: date
    available: bool
    min_length_of_stay: int
    avg_price_display: str | None


@dataclass(frozen=True)
class CalendarResult:
    ok: bool
    days: tuple[CalendarDay, ...] = field(default_factory=tuple)
    error: str | None = None

    def day(self, d: date) -> CalendarDay | None:
        for cd in self.days:
            if cd.checkin == d:
                return cd
        return None


@dataclass(frozen=True)
class DemandSignal:
    kind: DemandKind
    value: Decimal
    window_hours: int | None = None
    stay_date: date | None = None  # None: tín hiệu cả khách sạn, không theo đêm
    raw_text: str | None = None


@dataclass(frozen=True)
class ListingIdentity:
    """Kết quả verify một listing: kênh trả về khách sạn nào."""

    external_id: str | None
    name: str | None
    url: str | None = None
    address: str | None = None
    city: str | None = None
    country_code: str | None = None
    lat: float | None = None
    lng: float | None = None
    star_rating: Decimal | None = None


@dataclass(frozen=True)
class ListingQuery:
    """Tìm cùng một khách sạn trên kênh khác (D8)."""

    name: str
    city: str | None = None
    country_code: str = "vn"
    lat: float | None = None
    lng: float | None = None


@dataclass(frozen=True)
class ListingCandidate:
    channel: str
    listing_key: str
    url: str
    name: str
    external_id: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    country_code: str | None = None
    score: float = 0.0  # 0..1, độ giống tên + khoảng cách toạ độ
