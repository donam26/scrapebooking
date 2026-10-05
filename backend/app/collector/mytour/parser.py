"""Đọc JSON API Mytour thành RoomOffer/ListingIdentity/ứng viên gợi ý. Thuần, không I/O.

Mytour là chợ nhiều nguồn: mỗi loại phòng có nhiều giá từ các nguồn khác nhau, phân biệt bằng
`rateCode` + `agencyId` ("ota:4", "ota:32" giá xác nhận ngay; "ta:27" giá đại lý, xác nhận sau
~15 phút). `availableAllotment` là số phòng còn của riêng giá đó (0 = nguồn không công bố).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.collector.mytour.urls import canonical_url
from app.domain.models import (
    DemandKind,
    DemandSignal,
    ListingIdentity,
    RatePlan,
    RoomOffer,
    StockScope,
)

PARSER_VERSION = "2"

# Web chỉ hiện "Vừa được đặt …" khi lần đặt cuối trong 5 ngày, và hiển thị
# dayjs(lastBookedTime/5).from(now/5): khoảng thời gian hiện ra bị chia 5 (63 giờ → "13 giờ").
_LAST_BOOKED_SHOWN_FOR = timedelta(days=5)
_LAST_BOOKED_DISPLAY_DIVISOR = 5


@dataclass(frozen=True)
class Availability:
    completed: bool  # False: máy chủ còn đang gom giá từ các nguồn, gọi lại sau
    offers: tuple[RoomOffer, ...]
    demand_signals: tuple[DemandSignal, ...] = ()


@dataclass(frozen=True)
class Suggestion:
    hotel_id: int
    name: str
    url: str
    address: str | None
    lat: float | None
    lng: float | None
    country_code: str | None


def parse_availability(
    data: dict[str, Any], adults: int, currency: str, now: datetime
) -> Availability:
    """`data` của rooms/availability. `currency` là tiền tệ đã yêu cầu, dùng khi giá không ghi."""
    items = data.get("items") or []
    offers = []
    for room in items:
        if room.get("outOfRoom"):
            continue
        max_guests = _int(room.get("maxGuests"))
        if max_guests is not None and max_guests < adults:
            continue
        public = [r for r in room.get("rates") or [] if _is_public_rate(r, adults)]
        if not public:
            continue
        rates = [_rate_plan(r, max_guests, currency) for r in public]
        # Mỗi nguồn công bố số phòng riêng, không cộng được: lấy số lớn nhất làm cận dưới.
        allotments = [_int(r.get("availableAllotment")) or 0 for r in public]
        offers.append(
            RoomOffer(
                external_room_id=str(room["roomKey"]),
                name=str(room.get("name") or "").strip(),
                max_occupancy=max_guests,
                badge_count=max(allotments, default=0) or None,
                dropdown_max=None,
                rates=tuple(sorted(rates, key=lambda p: p.price)),
                stock_scope=StockScope.RATE,
            )
        )
    last_booked = _last_booked(items, now)
    return Availability(
        completed=bool(data.get("completed")),
        offers=tuple(offers),
        demand_signals=(last_booked,) if last_booked else (),
    )


def _last_booked(items: list[dict[str, Any]], now: datetime) -> DemandSignal | None:
    """`lastBookedTime` (ms) giống nhau ở mọi phòng: là của cả khách sạn."""
    times = [t for t in (_int(room.get("lastBookedTime")) for room in items) if t]
    if not times:
        return None
    age = now - datetime.fromtimestamp(max(times) / 1000, tz=UTC)
    if age < timedelta(0) or age > _LAST_BOOKED_SHOWN_FOR:
        return None
    return DemandSignal(
        kind=DemandKind.LAST_BOOKED_MINUTES,
        value=Decimal(int(age.total_seconds() // 60)),  # thời gian thật, không chia 5
        raw_text=f"Vừa được đặt {_ago_label(age / _LAST_BOOKED_DISPLAY_DIVISOR)}",
    )


def _ago_label(age: timedelta) -> str:
    minutes = round(age.total_seconds() / 60)
    if minutes < 60:
        return f"{max(minutes, 1)} phút trước"
    hours = round(minutes / 60)
    return f"{hours} giờ trước" if hours < 24 else f"{round(hours / 24)} ngày trước"


def _is_public_rate(rate: dict[str, Any], adults: int) -> bool:
    """Bỏ giá phải đăng nhập (hiddenPrice: "Đăng nhập để giảm…"), giá giả, giá cho ít người hơn."""
    if rate.get("hiddenPrice") or rate.get("memberOnly") or rate.get("fake"):
        return False
    if not isinstance(rate.get("price"), int | float) or rate["price"] <= 0:
        return False
    occupancies = (rate.get("priceDetail") or {}).get("occupancies") or []
    return all((_int(o.get("adultNum")) or adults) >= adults for o in occupancies)


def _rate_plan(rate: dict[str, Any], max_guests: int | None, currency: str) -> RatePlan:
    # `price` = giá/phòng/đêm khách thấy, đã gồm thuế phí và KM tự áp; chưa trừ mã giảm giá phải
    # nhập tay (promotions[].code, hiện "Nhập mã: …" trên trang).
    price = Decimal(str(rate["price"]))
    before = (rate.get("promotionInfo") or {}).get("priceBeforePromotion")
    original = Decimal(str(before)).quantize(Decimal(1)) if before else None
    codes = [str(p["code"]) for p in rate.get("promotions") or [] if p.get("code")]
    breakfast = rate.get("freeBreakfast")
    name = str(rate.get("shortCancelPolicy") or "Giá phòng")
    return RatePlan(
        name=f"{name} · Bữa sáng" if breakfast else name,
        price=price,
        currency=_currency(rate.get("formattedPrice")) or currency,
        refundable=rate.get("freeCancellation"),
        breakfast=breakfast,
        max_persons=max_guests,
        price_original=original if original and original > price else None,
        taxes_included=True if rate.get("includedVAT") else None,
        promo_label=", ".join(codes) or None,
        source_supplier=f"{rate.get('rateCode')}:{rate.get('agencyId')}",
    )


def _currency(formatted: object) -> str | None:
    """ "1.808.000 VND" → "VND"."""
    if not isinstance(formatted, str) or not formatted.strip():
        return None
    code = formatted.split()[-1]
    return code if code.isalpha() and code.isupper() else None


def parse_identity(data: dict[str, Any]) -> ListingIdentity:
    """`data` của hotels/detail."""
    address = data.get("address") or {}
    coord = address.get("coordinate") or data.get("location") or {}
    hotel_id = data["id"]
    star = data.get("starNumber")
    return ListingIdentity(
        external_id=str(hotel_id),
        name=data.get("name"),
        url=canonical_url(hotel_id, data["slug"]) if data.get("slug") else None,
        address=address.get("address"),
        city=address.get("provinceName"),
        country_code=(address.get("countryCode") or "").lower() or None,
        lat=_float(coord.get("latitude")),
        lng=_float(coord.get("longitude")),
        star_rating=Decimal(str(star)) if star else None,
    )


def parse_suggestions(data: dict[str, Any]) -> list[Suggestion]:
    """`data` của suggestions/auto-complete: chỉ lấy mục là khách sạn (bỏ tỉnh, quận, chuỗi)."""
    out = []
    for item in data.get("items") or []:
        if item.get("type") != "HOTEL" or not item.get("hotelId"):
            continue
        address = item.get("address") or {}
        coord = address.get("coordinate") or {}
        slug = item.get("slug") or "khach-san"  # Mytour chỉ đọc id, slug sai vẫn chuyển hướng đúng
        out.append(
            Suggestion(
                hotel_id=int(item["hotelId"]),
                name=str(item.get("name") or ""),
                url=canonical_url(item["hotelId"], slug),
                address=address.get("address"),
                lat=_float(coord.get("latitude")),
                lng=_float(coord.get("longitude")),
                country_code="vn" if address.get("countryId") == 1 else None,
            )
        )
    return out


def _int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None
