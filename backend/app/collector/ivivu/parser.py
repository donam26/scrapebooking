"""Parser JSON/HTML của ivivu (thuần, không I/O).

Giá phòng (`HotelSearchReqContractAppV2`): `Hotels[0].RoomClasses[]`, mỗi hạng phòng có
`MealTypeRates[]` gộp nhiều nguồn bán (hợp đồng ivivu, B2B, Agoda, Hotelbeds, MGB…). Web hiện mỗi
gói ăn một giá, phần còn lại nằm sau "Xem thêm N lựa chọn khác": khách vẫn thấy và đặt được nên
giữ tất cả. Giá khách thấy ("Giá 1 đêm / 1 phòng") là `PriceAvgPlusTA`, đã gồm thuế phí khi
`ExcludeVAT = 0` (web ghi "Đã bao gồm thuế & phí").
"""

import json
import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.models import (
    DemandKind,
    DemandSignal,
    ListingIdentity,
    ProbeStatus,
    RatePlan,
    RoomOffer,
    StockScope,
)

# 2: không lọc Isshowprices=0 (Park Hyatt 01/10 bị coi là hết phòng)
# 3: tồn phòng từ AvailableNo (capped, scope rate); thiếu ExcludeVAT → taxes_included=None
PARSER_VERSION = "3"
INVALID_TOKEN = "Invalid_token_ivv"

_SUPPLIER_ALIASES = {"AGD": "AGODA", "INTERNAL": "IVIVU"}
_BREAKFAST_CODES = {"BB", "HB", "FB", "FI", "AI"}  # RO = chỉ phòng
_NG_STATE_RE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)

# Trường giữ lại khi lưu payload thô: đủ để parse lại, bỏ dữ liệu nội bộ của ivivu (email đối tác
# B2B, giá net, ghi chú bán hàng) và ảnh/mô tả (payload gốc ~3 MB).
_KEEP_TOP = ("Supplier", "MSG")
_KEEP_HOTEL = ("HotelCode", "HotelName", "CheckInDate", "CheckOutDate", "TotalNight", "ExcludeVAT")
_KEEP_CLASS = (
    "ClassID",
    "ClassName",
    "CurrencyCode",
    "Status",
    "Supplier",
    "SupplierCode",
    "IsPackageRate",
    "ExcludeVAT",
    "AvailableNo",
)
_KEEP_ROOM = ("MaxAdults", "MaxPax", "MaxChils")
_KEEP_RATE = (
    "RoomName",
    "Code",
    "Name",
    "Adults",
    "PriceAvgPlusTA",
    "PriceAvgPlusOTA",
    "PriceDiscount",
    "TotalTaxAndServiceFee",
    "PromotionNote",
    "Supplier",
    "Status",
    "AvailableNo",
    "IsPackageRate",
    "IsComboFlight",
    "Isshowprices",
)
_KEEP_PENALTY = ("IsPenaltyFree", "Penalty_Date")


@dataclass(frozen=True)
class ParsedPrice:
    status: ProbeStatus
    offers: tuple[RoomOffer, ...] = ()
    hotel_name: str | None = None
    error: str | None = None


def is_invalid_token(status: int, text: str) -> bool:
    return status == 403 and INVALID_TOKEN in text[:2000]


def parse_price_response(text: str, adults: int, currency: str) -> ParsedPrice:
    """Không bao giờ ném: payload lạ (ivivu đổi cấu trúc, trang chặn lọt vào) → ERROR để job ghi
    lỗi của đêm đó thay vì nổ cả job. SOLD_OUT chỉ khi payload hợp lệ (có khách sạn) nói không còn
    phòng; `Hotels` rỗng là lỗi/chặn mềm phía API, không phải hết phòng."""
    try:
        return _parse_price(text, adults, currency)
    except Exception as exc:  # noqa: BLE001 - cấu trúc lạ: TypeError/KeyError/AttributeError…
        return ParsedPrice(ProbeStatus.ERROR, error=f"malformed: {type(exc).__name__}: {exc}")


def _parse_price(text: str, adults: int, currency: str) -> ParsedPrice:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ParsedPrice(ProbeStatus.ERROR, error="invalid_json")
    if not isinstance(data, dict):
        return ParsedPrice(ProbeStatus.ERROR, error="invalid_json")
    if data.get("error_code"):
        return ParsedPrice(ProbeStatus.ERROR, error=f"api: {data['error_code']}")
    if "Hotels" not in data:
        return ParsedPrice(ProbeStatus.ERROR, error="malformed: no Hotels")
    hotels = data["Hotels"]
    if not isinstance(hotels, list) or not hotels or not isinstance(hotels[0], dict):
        # Hết phòng thật vẫn trả Hotels[0] (HotelCode, HotelName) với RoomClasses rỗng.
        return ParsedPrice(ProbeStatus.ERROR, error="empty_hotels")
    hotel = hotels[0]
    name = hotel.get("HotelName") or None
    hotel_vat = _opt_int(hotel.get("ExcludeVAT"))
    offers: dict[str, RoomOffer] = {}
    for rc in hotel.get("RoomClasses") or []:
        taxes = _taxes_included(hotel_vat, _opt_int(rc.get("ExcludeVAT")))
        rates: list[RatePlan] = []
        counts = [_positive(rc.get("AvailableNo"))]
        for raw in rc.get("MealTypeRates") or []:
            rate = _rate(raw, adults, currency, taxes)
            if rate is None:
                continue
            rates.append(rate)
            counts.append(_positive(raw.get("AvailableNo")))
        if not rates or rc.get("IsPackageRate"):
            continue
        rc_currency = rc.get("CurrencyCode") or currency
        if rc_currency != currency:
            return ParsedPrice(
                ProbeStatus.ERROR, hotel_name=name, error=f"currency_mismatch:{rc_currency}"
            )
        offer = _offer(rc, rates, max((c for c in counts if c), default=None))
        prev = offers.get(offer.external_room_id)
        if prev is not None:  # cùng hạng phòng lặp lại: gộp giá, tồn phòng lấy số lớn hơn
            known = [c for c in (prev.badge_count, offer.badge_count) if c]
            offer = replace(
                prev, rates=prev.rates + offer.rates, badge_count=max(known) if known else None
            )
        offers[offer.external_room_id] = offer
    if not offers:
        return ParsedPrice(ProbeStatus.SOLD_OUT, hotel_name=name)
    ordered = sorted(
        (replace(o, rates=tuple(sorted(o.rates, key=lambda r: r.price))) for o in offers.values()),
        key=lambda o: o.min_price or Decimal(0),
    )
    return ParsedPrice(ProbeStatus.OK, offers=tuple(ordered), hotel_name=name)


def _offer(rc: dict[str, Any], rates: list[RatePlan], available: int | None) -> RoomOffer:
    """`available` = max `AvailableNo` của hạng phòng và các dòng giá còn giữ, hiểu là "còn ÍT NHẤT
    N" (badge_count + scope rate → derive_stock cho `capped`), không phải tồn kho chính xác:
    - AvailableNo là allotment của từng nguồn bán (hợp đồng ivivu, B2B, Agoda, Hotelbeds…): trong
      một hạng phòng mỗi dòng giá một số (Park Hyatt 01/10: 1, 6, 7). Khách sạn còn ≥ max.
    - Nguồn ngoài chưa ghép (ClassID âm) luôn ghi 1: chỗ giữ "còn phòng", không phải đúng 1 (exact
      sẽ sinh cảnh báo sắp hết phòng giả).
    - Hạng phòng Status "RQ" (xác nhận sau) ghi 0 ở cấp hạng phòng dù dòng giá ghi 8–10 (Melia
      12/10): 0 không phải hết phòng, nên chỉ lấy số dương.
    Không dùng dropdown_max: ivivu không có ô chọn số phòng và derive_stock chỉ coi dropdown là
    capped khi chạm trần trang."""
    rooms = rc.get("Rooms") or [{}]
    return RoomOffer(
        external_room_id=room_class_id(rc),
        name=str(rc.get("ClassName") or ""),
        max_occupancy=_int(rooms[0].get("MaxAdults")) or None,
        badge_count=available,
        dropdown_max=None,
        rates=tuple(rates),
        stock_scope=StockScope.RATE,
    )


def _taxes_included(*exclude_vat: int | None) -> bool | None:
    """`ExcludeVAT` 0 = giá đã gồm thuế phí (web ghi "Đã bao gồm thuế & phí"), 1 = chưa. Thiếu ở
    cả khách sạn lẫn hạng phòng → None: không chắc, không đem so chéo kênh."""
    known = [v for v in exclude_vat if v is not None]
    if not known:
        return None
    return all(v == 0 for v in known)


def room_class_id(rc: dict[str, Any]) -> str:
    """ClassID dương là hạng phòng của ivivu (ổn định). ClassID âm là phòng nguồn ngoài chưa ghép,
    đánh số lại mỗi lần gọi: dùng tên làm khoá."""
    cid = _int(rc.get("ClassID"))
    if cid > 0:
        return str(cid)
    name = unicodedata.normalize("NFKD", str(rc.get("ClassName") or "").lower().replace("đ", "d"))
    ascii_name = "".join(c for c in name if not unicodedata.combining(c))
    return "name:" + re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def _rate(r: dict[str, Any], adults: int, currency: str, taxes: bool | None) -> RatePlan | None:
    # Không lọc theo `Isshowprices`: giá AGD/MGB của Park Hyatt (01/10) có Isshowprices=0 mà vẫn
    # đặt được, bằng giá trên Agoda/Trip.com; lọc thì cả khách sạn bị coi là hết phòng.
    if r.get("IsPackageRate") or r.get("IsComboFlight"):
        return None
    persons = _int(r.get("Adults"))  # 0: nguồn không ghi (Agoda)
    if 0 < persons < adults:
        return None
    price = _vnd(r.get("PriceAvgPlusTA")) or _vnd(r.get("PriceAvgPlusOTA"))
    if price is None or price <= 0:
        return None
    discount = _vnd(r.get("PriceDiscount"))
    penalties = r.get("Penaltys") or []
    return RatePlan(
        name=str(r.get("Name") or r.get("Code") or ""),
        price=price,
        currency=currency,
        refundable=bool(penalties[0].get("IsPenaltyFree")) if penalties else None,
        breakfast=_breakfast(r),
        max_persons=persons or None,
        price_original=price + discount if discount and discount > 0 else None,
        taxes_included=taxes,
        promo_label=(str(r.get("PromotionNote") or "").strip() or None),
        source_supplier=_supplier(r.get("Supplier")),
    )


def _breakfast(r: dict[str, Any]) -> bool | None:
    code = str(r.get("Code") or "").upper()
    if code == "RO":
        return False
    if code in _BREAKFAST_CODES:
        return True
    return None


def _supplier(raw: Any) -> str | None:
    value = str(raw or "").strip().upper()
    return _SUPPLIER_ALIASES.get(value, value) or None


def trim_price_payload(text: str) -> str:
    """Payload để lưu kho (S3): chỉ các trường parser dùng. Không phải JSON thì trả nguyên văn."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict) or "Hotels" not in data:
        return text
    out = _pick(data, _KEEP_TOP)
    out["Hotels"] = [
        {
            **_pick(h, _KEEP_HOTEL),
            "RoomClasses": [_trim_class(rc) for rc in h.get("RoomClasses") or []],
        }
        for h in data.get("Hotels") or []
    ]
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def _trim_class(rc: dict[str, Any]) -> dict[str, Any]:
    out = _pick(rc, _KEEP_CLASS)
    out["Rooms"] = [_pick(room, _KEEP_ROOM) for room in (rc.get("Rooms") or [])[:1]]
    out["MealTypeRates"] = [
        {
            **_pick(r, _KEEP_RATE),
            "Penaltys": [_pick(p, _KEEP_PENALTY) for p in (r.get("Penaltys") or [])[:1]],
        }
        for r in rc.get("MealTypeRates") or []
    ]
    return out


def _pick(d: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: d[k] for k in keys if k in d}


def parse_hotel_page(html: str, url: str | None = None) -> ListingIdentity | None:
    """Trang khách sạn render sẵn (SSR) dữ liệu `GetHotelDetailV3` trong <script id="ng-state">."""
    m = _NG_STATE_RE.search(html)
    if not m:
        return None
    try:
        state = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    for entry in state.values() if isinstance(state, dict) else ():
        body = entry.get("b") if isinstance(entry, dict) else None
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            continue
        hotel = data.get("hotel")
        if not isinstance(hotel, dict) or not hotel.get("id"):
            continue
        crumbs = [c.get("text") for c in data.get("breadcrumbs") or [] if c.get("level", 0) >= 3]
        path = str(hotel.get("url") or "").strip("/")
        return ListingIdentity(
            external_id=str(hotel["id"]),
            name=(hotel.get("name") or "").strip() or None,
            url=f"https://www.ivivu.com/{path}" if path else url,
            address=(hotel.get("address") or "").strip() or None,
            city=(crumbs[-1] if crumbs else None) or hotel.get("province") or None,
            country_code=(hotel.get("countryCode") or "vn").lower(),
            lat=_float(hotel.get("latitude")),
            lng=_float(hotel.get("longitude")),
            star_rating=_stars(hotel.get("rating")),
        )
    return None


def parse_search(text: str) -> list[dict[str, Any]]:
    """Kết quả `searchhotel`: chỉ giữ khách sạn (type 1), bỏ vùng/địa danh."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict) and d.get("type") == 1 and d.get("hotelId")]


def top_sale_signal(text: str) -> DemandSignal | None:
    """`TopSale24hByHotel` → "Đã bán N phòng trong 24 giờ qua" (web chỉ hiện khi N > 0)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    total = data.get("total") if isinstance(data, dict) else None
    if not isinstance(total, int):
        return None
    return DemandSignal(
        kind=DemandKind.ROOMS_SOLD_24H,
        value=Decimal(total),
        window_hours=24,
        raw_text=f"Đã bán {total} phòng trong 24 giờ qua (TopSale24hByHotel)",
    )


def bookings_month_signal(item: dict[str, Any]) -> DemandSignal | None:
    count = item.get("bookingInMonth")
    if not isinstance(count, int):
        return None
    return DemandSignal(
        kind=DemandKind.BOOKINGS_MONTH,
        value=Decimal(count),
        raw_text=f"bookingInMonth={count} (searchhotel)",
    )


def _stars(raw: Any) -> Decimal | None:
    value = _decimal(raw)  # ivivu ghi sao x10: 50 = 5 sao, 45 = 4,5 sao
    return value / 10 if value else None


def _int(raw: Any) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _opt_int(raw: Any) -> int | None:
    """Số nguyên, None nếu thiếu/không đọc được (khác _int: thiếu không thành 0)."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _positive(raw: Any) -> int | None:
    value = _opt_int(raw)
    return value if value is not None and value > 0 else None


def _decimal(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _vnd(raw: Any) -> Decimal | None:
    value = _decimal(raw)
    return value.quantize(Decimal(1)) if value is not None else None


def _float(raw: Any) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
