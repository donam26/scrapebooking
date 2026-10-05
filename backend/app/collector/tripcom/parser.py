"""Parser Trip.com (thuần, không I/O).

- Trang khách sạn (SSR Next.js): dữ liệu nằm trong các chunk `self.__next_f.push([1,"…"])`; khối
  `hotelDetailResponse` có tên, hạng sao, địa chỉ, toạ độ và "Lần đặt gần nhất cách đây N phút".
- Danh sách phòng: JSON của `getHotelRoomListOversea`. `roomList` là thứ tự hiển thị (loại phòng
  vật lý → các mức giá `skey`), chi tiết nằm ở `physicRoomMap` / `saleRoomMap`.

Chuẩn giá (D3): `priceInfo.price` là giá TB/đêm CHƯA thuế; `comparingAmount` là tổng cả kỳ ở
(1 phòng × N đêm) ĐÃ gồm thuế phí → giá chuẩn = comparingAmount / N. `deletePrice` (giá gạch) cùng
cơ sở với `priceInfo.price` nên quy về gồm thuế theo cùng tỉ lệ thuế.

Tồn phòng (D4): `bookingStatusInfo.remainRoomQuantity` là số phòng còn của MỨC GIÁ đó (chính là số
trong "Chỉ còn N phòng có giá này" ở trang danh sách; 9999 = không giới hạn); `ruleInfo.maxQuantity`
là ô chọn số phòng (trần 10).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.domain.models import DemandKind, DemandSignal, ProbeStatus, RatePlan, RoomOffer

PARSER_VERSION = "2"  # 2: tính "Gói Khách Sạn" (nhãn gói), loại combo; lưu là "tripcom:2"

UNLIMITED_ROOMS = 9999  # remainRoomQuantity khi kênh không giới hạn (free sale)
_COUNTRY_CODES = {111: "vn"}  # countryId của Trip.com
_BREAKFAST_MEAL_TYPES = {4, 5, 7}  # 4 bữa sáng, 5 sáng + tối, 7 ba bữa
_MEAL_SUFFIX = {4: "", 5: " + tối", 7: " + trưa + tối"}
_CANCEL_NON_REFUNDABLE = 5

_FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_LAST_BOOKING_RE = re.compile(r'lastBooking\\*"\s*:\s*\\*"([^"\\]+)')
_AGO_RE = re.compile(r"(\d+)\s*(phút|giờ|ngày|minute|hour|day)", re.IGNORECASE)
_AGO_MINUTES = {"phút": 1, "minute": 1, "giờ": 60, "hour": 60, "ngày": 1440, "day": 1440}

_HOTEL_PACKAGE = 2  # xProOption.pkType của "Gói Khách Sạn" (phòng + quyền lợi của khách sạn)
# Thành phần gói không phải của khách sạn (combo vé máy bay, đưa đón, tour) → loại khỏi so giá (D3).
_COMBO_RE = re.compile(
    r"vé máy bay|chuyến bay|\bflight|đưa\s*đón|\btransfer|\bshuttle|\btour\b", re.IGNORECASE
)


@dataclass(frozen=True)
class HotelPage:
    """Thông tin tĩnh của khách sạn lấy từ trang chi tiết (SSR)."""

    hotel_id: str | None
    name: str | None
    name_en: str | None = None
    address: str | None = None
    city: str | None = None
    country_code: str | None = None
    lat: float | None = None
    lng: float | None = None
    star_rating: Decimal | None = None
    last_booking: str | None = None  # "Lần đặt gần nhất cách đây 18 phút"


@dataclass(frozen=True)
class RoomListResult:
    status: ProbeStatus
    offers: tuple[RoomOffer, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SuggestHit:
    hotel_id: str
    name: str
    subtitle: str | None
    lat: float | None
    lng: float | None
    country_code: str | None


@dataclass(frozen=True)
class ParsedProbe:
    page: HotelPage
    result: RoomListResult
    demand_signals: tuple[DemandSignal, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- trang khách sạn (SSR)


def decode_flight(html: str) -> str:
    """Ghép các chunk RSC (chuỗi JS đã escape) thành văn bản."""
    parts: list[str] = []
    for chunk in _FLIGHT_CHUNK_RE.findall(html):
        try:
            parts.append(json.loads(f'"{chunk}"'))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def extract_object(text: str, key: str) -> dict[str, Any] | None:
    """Object JSON đầu tiên đứng sau `"key":` trong văn bản."""
    marker = f'"{key}":'
    start = text.find(marker)
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start + len(marker))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f not in (0.0, -1.0) else None


def parse_hotel_page(html: str) -> HotelPage:
    detail = extract_object(decode_flight(html), "hotelDetailResponse") or {}
    base = detail.get("hotelBaseInfo") or {}
    position = detail.get("hotelPositionInfo") or {}
    names = base.get("nameInfo") or {}
    star = (base.get("starInfo") or {}).get("level")
    hotel_id = base.get("masterHotelId")
    last_booking = base.get("lastBooking")
    if not last_booking:
        m = _LAST_BOOKING_RE.search(html)
        last_booking = m.group(1) if m else None
    return HotelPage(
        hotel_id=str(hotel_id) if hotel_id else None,
        name=names.get("name") or names.get("nameEn") or None,
        name_en=names.get("nameEn") or None,
        address=position.get("address") or None,
        city=base.get("cityName") or None,
        country_code=_COUNTRY_CODES.get(base.get("countryId") or 0),
        lat=_float(position.get("lat")),
        lng=_float(position.get("lng")),
        star_rating=Decimal(str(star)) if isinstance(star, int | float) and star > 0 else None,
        last_booking=last_booking or None,
    )


def last_booked_minutes(text: str) -> int | None:
    """ "Lần đặt gần nhất cách đây 18 phút" → 18; "… 15 giờ trước" → 900."""
    m = _AGO_RE.search(text)
    if not m:
        return None
    return int(m.group(1)) * _AGO_MINUTES[m.group(2).lower()]


def demand_signals(page: HotelPage) -> tuple[DemandSignal, ...]:
    if not page.last_booking:
        return ()
    minutes = last_booked_minutes(page.last_booking)
    if minutes is None:
        return ()
    return (
        DemandSignal(
            kind=DemandKind.LAST_BOOKED_MINUTES,
            value=Decimal(minutes),
            raw_text=page.last_booking,
        ),
    )


# ---------------------------------------------------------------- danh sách phòng (API)


def is_spider_blocked(payload: dict[str, Any]) -> bool:
    return (payload.get("data") or {}).get("htlSpiderActionErrorCode") is not None


def _api_error(payload: dict[str, Any]) -> str | None:
    status = payload.get("ResponseStatus") or {}
    if status.get("Ack") in (None, "Success"):
        return None
    errors = status.get("Errors") or []
    message = errors[0].get("Message") if errors and isinstance(errors[0], dict) else None
    return f"api: {message or status.get('Ack')}"


def _searched(data: dict[str, Any]) -> tuple[str, str, int] | None:
    box = data.get("searchBoxInfo") or {}
    if not box.get("checkIn"):
        return None
    return str(box.get("checkIn")), str(box.get("checkOut")), int(box.get("adult") or 0)


def _bookable(sale: dict[str, Any]) -> bool:
    status = sale.get("bookingStatusInfo") or {}
    return status.get("isBooking", True) is not False and not status.get("isFullRoom")


def _package_items(sale: dict[str, Any]) -> list[tuple[str, str]]:
    """(title, name) của các thành phần gói, VD ("Bao gồm", "Đặc quyền Signature Lounge")."""
    products = (sale.get("xProOption") or {}).get("xProducts") or []
    return [(str(p.get("title") or ""), str(p.get("name") or "")) for p in products]


def _is_combo(sale: dict[str, Any]) -> bool:
    """Combo không thuộc khách sạn (loại gói lạ, hoặc kèm vé máy bay/đưa đón/tour) → bỏ (D3).
    "Gói Khách Sạn" (pkType 2: lounge, spa, bữa ăn…) vẫn được tính, kèm nhãn gói."""
    pk_type = (sale.get("xProOption") or {}).get("pkType") or 0
    if pk_type not in (0, _HOTEL_PACKAGE):
        return True
    return any(_COMBO_RE.search(f"{title} {name}") for title, name in _package_items(sale))


def _package_label(sale: dict[str, Any]) -> str | None:
    if (sale.get("xProOption") or {}).get("pkType") != _HOTEL_PACKAGE:
        return None
    names = [name for _, name in _package_items(sale) if name]
    return (f"Gói khách sạn: {', '.join(names)}" if names else "Gói khách sạn")[:64]


def _whole(value: Decimal) -> Decimal:
    return value.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _refundable(sale: dict[str, Any]) -> bool | None:
    free = (sale.get("totalPriceInfo") or {}).get("isFreeCancel")
    if isinstance(free, bool):
        return free
    cancel_type = (sale.get("cancelInfo") or {}).get("type")
    if cancel_type == _CANCEL_NON_REFUNDABLE:
        return False
    return True if cancel_type in (1, 2, 3) else None


def _breakfast(sale: dict[str, Any]) -> bool | None:
    meal = sale.get("mealInfo") or {}
    if meal.get("mealFlag") == 0:
        return False
    return True if meal.get("mealType") in _BREAKFAST_MEAL_TYPES else None


def _rate_name(refundable: bool | None, breakfast: bool | None, meal_type: Any) -> str:
    if refundable is None:
        name = "Tiêu chuẩn"
    else:
        name = "Hủy miễn phí" if refundable else "Không hoàn tiền"
    if breakfast:
        name += " + bữa sáng" + _MEAL_SUFFIX.get(meal_type, "")
    return name


def _promo_label(sale: dict[str, Any], discounted: bool) -> str | None:
    """Tên gói khách sạn nếu có (giải thích giá cao hơn), không thì tên KM có số tiền > 0."""
    package = _package_label(sale)
    if package:
        return package
    total = sale.get("totalPriceInfo") or {}
    for tag in total.get("promotionTagList") or []:
        if (tag.get("amount") or 0) > 0 and tag.get("title"):
            return str(tag["title"])[:64]
    if discounted:
        for label in sale.get("priceLabelList") or []:
            if label.get("text"):
                return str(label["text"])[:64]
    return None


def _rate_plan(sale: dict[str, Any], nights: int) -> RatePlan | None:
    price_info = sale.get("priceInfo") or {}
    pre_tax = price_info.get("price")
    currency = price_info.get("currency")
    if not isinstance(pre_tax, int | float) or pre_tax <= 0 or not currency:
        return None
    pre_tax_dec = Decimal(str(pre_tax))
    total = sale.get("comparingAmount")
    if isinstance(total, int | float) and total >= pre_tax * nights:
        price = _whole(Decimal(str(total)) / nights)
        taxes_included: bool | None = True
    else:
        price, taxes_included = pre_tax_dec, False
    deleted = price_info.get("deletePricewithOutCurrency")
    original = None
    if isinstance(deleted, int | float) and deleted > pre_tax:
        original = _whole(Decimal(str(deleted)) * price / pre_tax_dec)
    refundable, breakfast = _refundable(sale), _breakfast(sale)
    guests = (sale.get("guestCountInfo") or {}).get("guestCount")
    return RatePlan(
        name=_rate_name(refundable, breakfast, (sale.get("mealInfo") or {}).get("mealType")),
        price=price,
        currency=str(currency),
        refundable=refundable,
        breakfast=breakfast,
        max_persons=guests if isinstance(guests, int) and guests > 0 else None,
        price_original=original,
        taxes_included=taxes_included,
        promo_label=_promo_label(sale, original is not None),
    )


def _rooms_left(sales: list[dict[str, Any]]) -> int | None:
    """Số còn của mức giá cho biết nhiều nhất về loại phòng: lớn nhất (cận dưới chặt nhất)."""
    counts = [
        c
        for c in ((s.get("bookingStatusInfo") or {}).get("remainRoomQuantity") for s in sales)
        if isinstance(c, int) and 0 < c < UNLIMITED_ROOMS
    ]
    return max(counts) if counts else None


def _dropdown_max(sales: list[dict[str, Any]]) -> int | None:
    values = [
        q
        for q in ((s.get("ruleInfo") or {}).get("maxQuantity") for s in sales)
        if isinstance(q, int) and q > 0
    ]
    return max(values) if values else None


def parse_room_list(
    payload: dict[str, Any],
    *,
    currency: str,
    adults: int,
    nights: int,
    checkin: date | None = None,
) -> RoomListResult:
    """Một RoomOffer cho mỗi loại phòng vật lý đang hiển thị. Giá: các mức đặt được, không phải
    combo (gói khách sạn vẫn tính), đủ chỗ cho `adults`. Tồn phòng: từ mọi mức đặt được, phạm vi
    "rate"."""
    if is_spider_blocked(payload):
        return RoomListResult(ProbeStatus.BLOCKED, error="htlSpiderActionErrorCode")
    error = _api_error(payload)
    data = payload.get("data")
    if error or not isinstance(data, dict):
        return RoomListResult(ProbeStatus.ERROR, error=error or "api: no data")
    searched = _searched(data)
    if checkin is not None and searched is not None:
        wanted = checkin.strftime("%Y%m%d")
        if searched[0] != wanted or searched[2] != adults:
            return RoomListResult(
                ProbeStatus.ERROR,
                error=f"tripcom showed other search: checkin {searched[0]} adults {searched[2]}",
            )
    physical = data.get("physicRoomMap") or {}
    sales = data.get("saleRoomMap") or {}
    groups = data.get("roomList") or []
    if not groups:
        status = ProbeStatus.SOLD_OUT if data.get("isRoomListSoldOut") else ProbeStatus.NO_ROOMS_1N
        return RoomListResult(status)

    offers: list[RoomOffer] = []
    for group in groups:
        room_id = str(group.get("key") or "")
        shown = [sales[s["skey"]] for s in group.get("subRoomList") or [] if s.get("skey") in sales]
        bookable = [s for s in shown if _bookable(s)]
        if not room_id or not bookable:
            continue
        for sale in bookable:
            cur = (sale.get("priceInfo") or {}).get("currency")
            if cur and cur != currency:
                return RoomListResult(ProbeStatus.ERROR, error=f"currency_mismatch:{cur}")
        rates = tuple(
            r
            for r in (_rate_plan(s, nights) for s in bookable if not _is_combo(s))
            if r and (r.max_persons is None or r.max_persons >= adults)
        )
        guests = [
            g
            for g in ((s.get("guestCountInfo") or {}).get("guestCount") for s in shown)
            if isinstance(g, int) and g > 0
        ]
        offers.append(
            RoomOffer(
                external_room_id=room_id,
                name=str((physical.get(room_id) or {}).get("name") or room_id),
                max_occupancy=max(guests) if guests else None,
                badge_count=_rooms_left(bookable),
                dropdown_max=_dropdown_max(bookable),
                rates=tuple(sorted(rates, key=lambda r: r.price)),
                stock_scope="rate",
            )
        )
    if not offers:
        return RoomListResult(ProbeStatus.SOLD_OUT)
    return RoomListResult(ProbeStatus.OK, tuple(offers))


# ---------------------------------------------------------------- payload lưu trữ


def build_payload(page: HotelPage, room_list_text: str) -> str:
    """Payload thô lưu MinIO: JSON API nguyên vẹn + vài trường của trang (tên, lần đặt gần nhất)."""
    page_part = json.dumps(
        {"hotelId": page.hotel_id, "name": page.name, "lastBooking": page.last_booking},
        ensure_ascii=False,
    )
    return f'{{"tripcom":1,"page":{page_part},"roomList":{room_list_text}}}'


def parse_probe_payload(
    text: str, *, currency: str, adults: int, nights: int, checkin: date | None = None
) -> ParsedProbe:
    """Parse lại payload đã lưu (hoặc JSON API trần)."""
    doc = json.loads(text)
    if "roomList" in doc and "tripcom" in doc:
        info = doc.get("page") or {}
        page = HotelPage(
            hotel_id=info.get("hotelId"),
            name=info.get("name"),
            last_booking=info.get("lastBooking"),
        )
        room_list = doc["roomList"]
    else:
        page, room_list = HotelPage(hotel_id=None, name=None), doc
    result = parse_room_list(
        room_list, currency=currency, adults=adults, nights=nights, checkin=checkin
    )
    return ParsedProbe(page, result, demand_signals(page))


# ---------------------------------------------------------------- gợi ý (getHotelKeywords)


def _display(info: dict[str, Any], key: str) -> str | None:
    for item in info.get("displayTexts") or []:
        if item.get("key") == key and item.get("value"):
            return str(item["value"])
    return None


def parse_suggest(payload: dict[str, Any]) -> list[SuggestHit]:
    keywords = ((payload.get("data") or {}).get("mainKeywordList") or {}).get("keywords") or []
    hits: list[SuggestHit] = []
    for entry in keywords:
        keyword = entry.get("keyword") or {}
        hotel_id = (keyword.get("hotelInfo") or {}).get("hotelId")
        info = keyword.get("keywordContentInfo") or {}
        if not hotel_id or info.get("tripType") != "H":
            continue
        coords = {c.get("coordinateType"): c for c in info.get("coordinateItemList") or []}
        point = coords.get("GOOGLE") or coords.get("NORMAL") or {}
        city = (
            ((entry.get("controlInfo") or {}).get("regionInfo") or {}).get("basicCityModel")
        ) or {}
        hits.append(
            SuggestHit(
                hotel_id=str(hotel_id),
                name=_display(info, "MAIN_TITLE") or str(info.get("keyword") or ""),
                subtitle=_display(info, "SUB_TITLE"),
                lat=_float(point.get("latitude")),
                lng=_float(point.get("longitude")),
                country_code=_COUNTRY_CODES.get(city.get("countryId") or 0),
            )
        )
    return hits
