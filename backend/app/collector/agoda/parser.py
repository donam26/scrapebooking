"""Parser JSON Agoda (thuần, không I/O).

Nguồn chính: `GetSecondaryData` (dữ liệu trang khách sạn: bảng phòng, giá gồm thuế, tồn phòng,
tín hiệu cầu). `room-grid` chỉ dùng để xác nhận hết phòng khi bảng phòng rỗng.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.collector.agoda.urls import BASE, parse_url
from app.domain.models import (
    DemandKind,
    DemandSignal,
    ListingIdentity,
    PageOutcome,
    RatePlan,
    RoomOffer,
    StockScope,
)

PARSER_VERSION = "2"  # tăng khi đổi cách đọc payload (lưu theo từng probe)
COUNTRY_CODES = {38: "vn"}  # countryId của Agoda -> ISO
_NUMBER_RE = re.compile(r"\d[\d.,]*")
_PROPERTY_ID_RES = (
    re.compile(r"propertyId:(\d+)"),
    re.compile(r"hotel_id=(\d+)"),
    re.compile(r'"propertyId":"?(\d+)'),
)


class PayloadError(ValueError):
    """Body không phải JSON object (trang chặn, HTML lỗi…)."""


@dataclass(frozen=True)
class AgodaPage:
    outcome: PageOutcome
    external_id: str | None
    hotel_name: str | None  # None + complete: Agoda không có khách sạn này (id sai/đã gỡ)
    currency: str | None  # tiền tệ Agoda thực trả
    checkin: date | None
    nights: int | None
    offers: tuple[RoomOffer, ...] = field(default_factory=tuple)
    demand_signals: tuple[DemandSignal, ...] = field(default_factory=tuple)
    # payload_complete(): thiếu tên ở payload chưa đủ là chặn mềm, không phải not_found.
    complete: bool = True


@dataclass(frozen=True)
class SuggestHit:
    property_id: str
    name: str
    city: str | None
    country_code: str | None


def load_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise PayloadError("not json") from exc
    if not isinstance(data, dict):
        raise PayloadError("not a json object")
    return data


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def payload_complete(data: dict[str, Any]) -> bool:
    """Agoda đã trả trọn dữ liệu cho id này: `roomGridData.isDataReady` và không có `error`.
    Payload như vậy mà không có tên khách sạn là Agoda nói rõ id không tồn tại (fixture
    not_found.json); thiếu tên ở payload chưa sẵn sàng / có lỗi là chặn mềm hoặc sự cố, không
    phải "không tồn tại"."""
    ready = _bool(_dict(data.get("roomGridData")).get("isDataReady")) is True
    return ready and not data.get("error")


def explicit_not_found(text: str) -> bool:
    """Payload GetSecondaryData đầy đủ nhưng không có khách sạn (xem payload_complete)."""
    data = load_json(text)
    return _text(_dict(data.get("hotelInfo")).get("name")) is None and payload_complete(data)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def _money(value: Any) -> Decimal | None:
    """Số tiền Agoda (float): số nguyên thì bỏ ".0", lẻ giữ nguyên; <= 0 coi như không có."""
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount.quantize(Decimal(1)) if amount == amount.to_integral_value() else amount


def _first_number(text: str | None) -> int | None:
    m = _NUMBER_RE.search(text or "")
    return int(re.sub(r"[.,]", "", m.group(0))) if m else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _refundable(rate: dict[str, Any]) -> bool | None:
    if _bool(rate.get("isFreeCancellation")):
        return True
    cancellation = _dict(rate.get("cancellation"))
    marker = f"{cancellation.get('symbol') or ''} {cancellation.get('title') or ''}".lower()
    if "non-refund" in marker or "không hoàn tiền" in marker:
        return False
    return None  # huỷ mất phí một phần: không phải miễn phí, cũng không phải không hoàn


def _promo_label(rate: dict[str, Any], coupon_applied: bool) -> str | None:
    """Tên chiến dịch ("Mùa thu vàng", "NOON FLASH") > coupon Agoda tự áp > nhãn KM chung."""
    label = (
        _text(_dict(rate.get("pulseCampaignInfo")).get("campaignBadgeText"))
        or ("Coupon" if coupon_applied else None)
        or _text(_dict(rate.get("promotion")).get("title"))
    )
    return label[:64] if label else None


def _campaign_discount(rate: dict[str, Any], price: Decimal) -> Decimal:
    """Phần giảm của chiến dịch Agoda (`corBreakdown.agodaPromotions` lớp "pulse-promo", VD "Mùa
    thu vàng"); KM của chính khách sạn ("Giảm giá phút chót") không tính. Chỉ dùng khi tổng cuối
    của bảng phân tích khớp `price` (cùng cơ sở gồm thuế/đêm)."""
    breakdown = _dict(rate.get("corBreakdown"))
    final = next(
        (
            _money(item.get("amount"))
            for item in map(_dict, _list(breakdown.get("priceSummaries")))
            if item.get("cssClass") == "final-price"
        ),
        None,
    )
    if final is None or abs(final - price) > 1:
        return Decimal(0)
    return sum(
        (
            _money(item.get("amount")) or Decimal(0)
            for item in map(_dict, _list(breakdown.get("agodaPromotions")))
            if item.get("cssClass") == "pulse-promo"
        ),
        Decimal(0),
    )


def _rate_plan(rate: dict[str, Any]) -> RatePlan | None:
    """Giá theo phòng/đêm: ưu tiên bản gồm thuế phí; chỉ có bản chưa thuế thì ghi rõ cờ."""
    prices = _dict(rate.get("inclusivePricePerNightWithoutExtraBed"))
    taxes_included = True
    if _money(prices.get("display")) is None:
        prices, taxes_included = _dict(rate.get("exclusivePrice")), False
    price = _money(prices.get("display"))
    currency = rate.get("currency")
    if price is None or not isinstance(currency, str):
        return None
    # price_original = giá trước coupon + chiến dịch Agoda tự áp. Không dùng giá gạch `crossedOut`
    # (COR, thường là "giá cao nhất ±30 ngày", hiện -75%).
    before_coupon = _money(prices.get("couponCrossedOut"))
    base = before_coupon if before_coupon is not None and before_coupon > price else price
    coupon_applied = base > price
    original = base + _campaign_discount(rate, price)
    refundable = _refundable(rate)
    breakfast = _bool(rate.get("isBreakfastIncluded"))
    if refundable is None:
        name = "Standard"
    else:
        name = "Free cancellation" if refundable else "Non-refundable"
    if breakfast:
        name += " + breakfast"
    return RatePlan(
        name=name,
        price=price,
        currency=currency,
        refundable=refundable,
        breakfast=breakfast,
        max_persons=_int(rate.get("occupancy")) or _int(rate.get("adults")),
        price_original=original if original > price else None,
        taxes_included=taxes_included,
        promo_label=_promo_label(rate, coupon_applied),
    )


def _is_package(master: dict[str, Any], rate: dict[str, Any]) -> bool:
    """Giá gói/combo hoặc gợi ý nhiều phòng: không phải giá 1 phòng lẻ."""
    if master.get("isMultiRoomSuggestion") or master.get("isMultiRoomBundle"):
        return True
    return bool(rate.get("stayPackageType") or rate.get("bundleType")) or (
        (_int(rate.get("numberOfFixRoom")) or 1) > 1
    )


def _room_offer(master: dict[str, Any], adults: int | None) -> RoomOffer | None:
    room_id = _int(master.get("id"))
    name = _text(master.get("name"))
    if room_id is None or name is None:
        return None
    rates: list[RatePlan] = []
    counts: list[int] = []
    for rate in map(_dict, _list(master.get("rooms"))):
        if _is_package(master, rate):
            continue
        count = _int(rate.get("availability"))
        if count is not None:
            counts.append(count)
        persons = _int(rate.get("adults"))
        if adults is not None and persons is not None and persons < adults:
            continue  # giá cho ít khách hơn số đã tìm (VD 1 người lớn)
        plan = _rate_plan(rate)
        if plan is not None:
            rates.append(plan)
    first = _int(master.get("firstRoomAvailability"))
    # `availability` là số phòng Agoda còn bán của loại phòng (cùng số ở mọi giá trong loại phòng,
    # khớp nhãn "Chỉ còn lại N phòng!" khi Agoda hiện). Không có dropdown số phòng ở API này.
    return RoomOffer(
        external_room_id=str(room_id),
        name=name,
        max_occupancy=_int(master.get("maxOccupancy")),
        badge_count=max(counts) if counts else first,
        dropdown_max=None,
        rates=tuple(rates),
        stock_scope=StockScope.ROOM_TYPE,
    )


def _sold_out_offer(room: dict[str, Any]) -> RoomOffer | None:
    room_id = _int(room.get("masterRoomId"))
    name = _text(room.get("masterRoomName"))
    if room_id is None or name is None:
        return None
    return RoomOffer(str(room_id), name, None, badge_count=0, dropdown_max=None)


def _demand_signals(info: dict[str, Any]) -> tuple[DemandSignal, ...]:
    """ "N du khách đã đặt hôm nay." (`visitorCount`, lúc có lúc không) = lượt đặt 24 giờ qua: trang
    hiện "Được đặt N lần trong vòng 24 giờ qua", GraphQL `timeFrame = PastTwentyFourHours`.
    "Đã được đặt N lần hôm nay" (`todayBooking`, luôn có) = lượt đặt trong ngày."""
    engagement = _dict(info.get("engagement"))
    signals: list[DemandSignal] = []
    for key, kind, window in (
        ("visitorCount", DemandKind.BOOKINGS_24H, 24),
        ("todayBooking", DemandKind.BOOKINGS_TODAY, None),
    ):
        raw = _text(engagement.get(key))
        count = _first_number(raw)
        if raw is not None and count is not None:
            signals.append(DemandSignal(kind, Decimal(count), window_hours=window, raw_text=raw))
    return tuple(signals)


def parse_property_data(text: str, adults: int | None = None) -> AgodaPage:
    """`adults`: số người lớn đã tìm; giá cho ít khách hơn bị bỏ (như Booking). None: giữ mọi
    giá."""
    data = load_json(text)
    info = _dict(data.get("hotelInfo"))
    criteria = _dict(data.get("hotelSearchCriteria"))
    grid = _dict(data.get("roomGridData"))
    hotel_id = _int(data.get("hotelId"))
    offers = [
        o for o in (_room_offer(_dict(m), adults) for m in _list(grid.get("masterRooms"))) if o
    ]
    sold_out = [
        o for o in (_sold_out_offer(_dict(s)) for s in _list(data.get("soldOutRooms"))) if o
    ]
    if offers:
        outcome = PageOutcome.ROOMS
    elif sold_out:
        outcome = PageOutcome.SOLD_OUT  # mọi loại phòng đều gắn "Hết phòng"
    else:
        outcome = PageOutcome.EMPTY  # khách sạn hết sạch phòng cũng trả rỗng: hỏi thêm room-grid
    currency = criteria.get("currencyCode")
    return AgodaPage(
        outcome=outcome,
        external_id=str(hotel_id) if hotel_id else None,
        hotel_name=_text(info.get("name")),
        currency=currency if isinstance(currency, str) else None,
        checkin=_date(criteria.get("checkInDate")),
        nights=_int(criteria.get("los")),
        offers=tuple(offers + sold_out),
        demand_signals=_demand_signals(info),
        complete=payload_complete(data),
    )


def parse_room_grid_sold_out(text: str) -> bool | None:
    """Cờ `isSoldOut` của API room-grid: True = Agoda báo hết phòng cho ngày đã chọn."""
    return _bool(load_json(text).get("isSoldOut"))


def parse_identity(text: str) -> ListingIdentity:
    """Định danh từ GetSecondaryData (có hoặc không kèm ngày). Khách sạn không tồn tại: name
    None."""
    data = load_json(text)
    info = _dict(data.get("hotelInfo"))
    name = _text(info.get("name"))
    if name is None:
        return ListingIdentity(external_id=None, name=None)
    address = _dict(info.get("address"))
    latlng = [
        v for v in _list(_dict(data.get("mapParams")).get("latlng")) if isinstance(v, int | float)
    ]
    lat, lng = (
        (float(latlng[0]), float(latlng[1])) if len(latlng) == 2 and any(latlng) else (None, None)
    )
    star = _dict(info.get("starRating")).get("value")
    hotel_id = _int(data.get("hotelId"))
    return ListingIdentity(
        external_id=str(hotel_id) if hotel_id else None,
        name=name,
        url=_canonical_from_search_url(
            _dict(_dict(data.get("searchbox")).get("config")).get("defaultSearchURL")
        ),
        address=_text(address.get("address")) or _text(address.get("full")),
        city=_text(address.get("cityName")),
        country_code=COUNTRY_CODES.get(_int(address.get("countryId")) or 0),
        lat=lat,
        lng=lng,
        star_rating=Decimal(str(star)) if isinstance(star, int | float) and star > 0 else None,
    )


def _canonical_from_search_url(value: Any) -> str | None:
    """ "/vi-vn/<slug>/hotel/<city>.html?checkIn=…" -> URL chuẩn không kèm ngày."""
    if not isinstance(value, str) or not value:
        return None
    try:
        listing = parse_url(BASE + urlparse(value).path)
    except ValueError:
        return None
    return listing.url if listing else None


def parse_suggest(text: str) -> list[SuggestHit]:
    hits: list[SuggestHit] = []
    for item in map(_dict, _list(load_json(text).get("ViewModelList"))):
        object_id = _int(item.get("ObjectId"))
        name = _text(item.get("Name"))
        if item.get("IsHotel") is not True or not object_id or name is None:
            continue
        iso = item.get("CountryISO")
        hits.append(
            SuggestHit(
                property_id=str(object_id),
                name=name,
                city=_text(item.get("CityName")),
                country_code=iso.lower() if isinstance(iso, str) and iso else None,
            )
        )
    return hits


def property_id_from_html(html: str) -> str | None:
    """propertyId trong HTML trang khách sạn (initParams / URL GetSecondaryData)."""
    for pattern in _PROPERTY_ID_RES:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None
