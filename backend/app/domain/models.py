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


class PageOutcome(StrEnum):
    ROOMS = "rooms"  # có bảng phòng với ít nhất 1 dòng
    SOLD_OUT = "sold_out"  # có thông báo hết phòng rõ ràng
    EMPTY = "empty"  # không có bảng phòng, không có thông báo: nghi bị chặn hoặc min stay


@dataclass(frozen=True)
class HotelRef:
    id: int
    country_code: str
    slug: str  # "vn/the-reverie-saigon"
    canonical_url: str

    @property
    def pagename(self) -> str:
        return self.slug.split("/", 1)[1]


@dataclass(frozen=True)
class RatePlan:
    name: str
    price: Decimal
    currency: str
    refundable: bool | None
    breakfast: bool | None
    max_persons: int | None = None  # "Max persons" của dòng giá (Booking có dòng riêng cho 1 khách)


@dataclass(frozen=True)
class RoomOffer:
    booking_room_id: str
    name: str
    max_occupancy: int | None
    badge_count: int | None
    dropdown_max: int | None
    rates: tuple[RatePlan, ...] = field(default_factory=tuple)

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
    booking_hotel_id: str | None
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
    booking_hotel_id: str | None = None
    hotel_name: str | None = None


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
