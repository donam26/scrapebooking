"""Parser kết quả tìm kiếm Booking.com (thuần).

Hai nguồn cùng một cấu trúc `search(...)` → `parse_search_entry`:
- Trang SSR: kho Apollo nhúng trong trang (`<script data-capla-store-data="apollo">`), đối tượng
  chuẩn hoá bằng `__ref`.
- JSON của GraphQL `FullSearch` (app/marketscan/graphql.py): đối tượng lồng trực tiếp.
Dự phòng: thẻ HTML `[data-testid=property-card]` khi trang không có kho này (thiếu id và toạ độ).

Khu vực sắp kín thì Booking "nới" tìm kiếm sang vùng lân cận (`totalAutoextendedAvailable`, thẻ
`persuasion.autoextended`). Các khách sạn đó không thuộc khu vực: bị loại khỏi `cards`, chỉ đếm;
`total` là số còn phòng TRONG khu vực (`totalAvailableNotAutoextended`).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from selectolax.parser import HTMLParser, Node

from app.channels.registry import UnsupportedUrl
from app.collector.booking.urls import canonical_url, parse_url

_APOLLO_RE = re.compile(
    r"<script[^>]*data-capla-store-data=\"apollo\"[^>]*>(.*?)</script>", re.DOTALL
)
_FOUND_RE = re.compile(r"(\d[\d,.]*)\s+propert(?:y|ies)\s+found", re.IGNORECASE)
_MONEY_RE = re.compile(r"([A-Z]{3})\s*(\d[\d,]*(?:\.\d+)?)")
_SCORE_RE = re.compile(r"Scored\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_REVIEWS_RE = re.compile(r"(\d[\d,]*)\s+reviews?", re.IGNORECASE)
_STARS_RE = re.compile(r"rating:\s*(\d)\s+out of 5", re.IGNORECASE)
_LEFT_RE = re.compile(r"(\d+)\s+left", re.IGNORECASE)  # "We have 3 left at this price"
IMAGE_HOST = "https://cf.bstatic.com"
# Nhóm facet trùng lặp nhóm khác hoặc không phản ánh truy vấn này (bộ lọc dùng gần đây).
SKIP_FACET_GROUPS = frozenset({"popular", "popular_sticky", "used_filters"})

Deref = Callable[[Any], dict[str, Any]]


@dataclass(frozen=True)
class SearchCard:
    slug: str  # "vn/ten-khach-san" (listing_key của kênh Booking)
    url: str  # URL chuẩn của trang khách sạn
    name: str
    external_id: str | None = None  # b_hotel_id
    review_score: Decimal | None = None  # thang 10
    review_count: int | None = None
    stars: Decimal | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    distance_text: str | None = None  # "0.7 km from centre"
    lat: float | None = None
    lng: float | None = None
    image_url: str | None = None
    price: Decimal | None = None  # cả kỳ ở (1 đêm), gồm thuế phí nếu trang ghi phần cộng thêm
    currency: str | None = None
    sold_out: bool = False
    type_id: int | None = None  # loại chỗ ở của kênh (ht_id: 204 khách sạn, 201 căn hộ…)
    # Vị trí hiển thị (roadmap 7.2): thẻ quảng cáo ("Ad"), Preferred / Preferred Plus, tên deal.
    sponsored: bool = False
    preferred: str | None = None  # preferred | preferred_plus
    badges: tuple[str, ...] = ()
    autoextended: bool = False  # Booking nới tìm kiếm ra ngoài khu vực mới thấy thẻ này
    only_left: int | None = None  # "We have N left at this price" (gói rẻ nhất của thẻ)


@dataclass(frozen=True)
class PriceHistogram:
    """Thanh "Ngân sách" của Booking: `bars` cột đều nhau từ `min` tới `max` (VND/đêm), chiều cao
    tương đối (cột cao nhất = 100), chỉ tính chỗ còn phòng khớp bộ lọc; chỗ đắt hơn `max` không
    nằm trong cột nào."""

    min: Decimal
    max: Decimal
    bars: tuple[int, ...]

    def to_json(self) -> dict[str, Any]:
        return {"min": int(self.min), "max": int(self.max), "bars": list(self.bars)}


@dataclass(frozen=True)
class SearchPage:
    total: int | None  # số chỗ ở còn phòng TRONG khu vực cho đêm đó (không tính phần nới thêm)
    checkin: date | None  # ngày nhận phòng trang thực sự hiển thị (None nếu không đọc được)
    cards: list[SearchCard]  # đã loại thẻ nới thêm
    source: str  # apollo | html | graphql
    per_page: int | None = None  # kênh báo số thẻ mỗi trang (20/25, chế độ cuộn vô hạn 15)
    offset: int | None = None  # offset trang thực sự dùng (kênh có thể bỏ qua offset yêu cầu)
    # Số chỗ ở theo từng lựa chọn bộ lọc của truy vấn này: {"class=3": 315, "ht_id=204": 471…}.
    facets: dict[str, int] = field(default_factory=dict)
    autoextended: int | None = None  # số chỗ ở Booking nới thêm ngoài khu vực
    low_availability: bool | None = None
    # % chỗ ở của khu vực đã kín, Booking tự tính trên TỔNG khu vực (có bộ lọc vẫn chia cho tổng
    # không lọc, nên chỉ có nghĩa khi truy vấn không lọc).
    unavailability_pct: int | None = None
    histogram: PriceHistogram | None = None
    rooms: int | None = None  # nbRooms kênh thực sự dùng (kẹp ≤ 30)
    adults: int | None = None
    raw_count: int = 0  # số kết quả kênh trả ở trang này (kể cả thẻ nới thêm): bước lật trang


def _money(value: Decimal, currency: str) -> Decimal:
    step = Decimal("1") if currency == "VND" else Decimal("0.01")
    return value.quantize(step, rounding=ROUND_HALF_UP)


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def district_of(display_location: str | None) -> str | None:
    """ "District 1, Ho Chi Minh City" → "District 1"; chỉ có tên thành phố → None."""
    parts = [p.strip() for p in (display_location or "").split(",") if p.strip()]
    return parts[0][:120] if len(parts) >= 2 else None


def only_left_of(message: str | None) -> int | None:
    m = _LEFT_RE.search(message or "")
    return int(m.group(1)) if m else None


def plain(obj: Any) -> dict[str, Any]:
    """Deref cho JSON GraphQL (đối tượng lồng trực tiếp)."""
    return obj if isinstance(obj, dict) else {}


def store_deref(store: dict[str, Any]) -> Deref:
    """Deref cho kho Apollo: `{"__ref": "Key"}` → đối tượng trong kho."""

    def deref(obj: Any) -> dict[str, Any]:
        if not isinstance(obj, dict):
            return {}
        ref = obj.get("__ref")
        return (store.get(ref) or {}) if isinstance(ref, str) else obj

    return deref


# ---- Một kết quả `search(...)` (kho Apollo hoặc GraphQL) ----


def _price(info: dict[str, Any], deref: Deref) -> tuple[Decimal | None, str | None]:
    shown = deref(deref(info.get("displayPrice")).get("amountPerStay"))
    amount, currency = _decimal(shown.get("amountUnformatted")), shown.get("currency")
    if not amount or not currency:
        return None, None
    excluded = deref(
        deref(deref(info.get("excludedCharges")).get("excludeChargesAggregated")).get(
            "amountPerStay"
        )
    )
    extra = _decimal(excluded.get("amountUnformatted"))
    if extra and (excluded.get("currency") or currency) == currency:
        amount += extra
    return _money(amount, currency), str(currency)


def _badge_text(badge: dict[str, Any]) -> str | None:
    """Huy hiệu giá: `name.translation`; huy hiệu thẻ: `name` chuỗi hoặc `caption.translation`."""
    name = badge.get("name")
    if isinstance(name, str):
        return name
    if isinstance(name, dict) and isinstance(name.get("translation"), str):
        return str(name["translation"])
    caption = badge.get("caption")
    if isinstance(caption, dict) and isinstance(caption.get("translation"), str):
        return str(caption["translation"])
    return None


def _card(raw: Any, deref: Deref) -> SearchCard | None:
    r = deref(raw)
    b = deref(r.get("basicPropertyData"))
    loc = deref(b.get("location"))
    page_name, cc = b.get("pageName"), str(loc.get("countryCode") or "").lower()
    if not page_name or len(cc) != 2:
        return None
    slug = f"{cc}/{page_name}"
    reviews = deref(b.get("reviews"))
    count = int(reviews.get("reviewsCount") or 0)
    score = _decimal(reviews.get("totalScore"))
    stars = _decimal(deref(b.get("starRating")).get("value"))
    photo = deref(deref(deref(b.get("photos")).get("main")).get("highResJpegUrl")).get(
        "relativeUrl"
    )
    shown = deref(r.get("location"))
    price_info = deref(r.get("priceDisplayInfoIrene"))
    price, currency = _price(price_info, deref)
    lat, lng = loc.get("latitude"), loc.get("longitude")
    pers = deref(r.get("persuasion"))
    preferred = (
        "preferred_plus"
        if pers.get("preferredPlus")
        else "preferred"
        if pers.get("preferred")
        else None
    )
    badges: list[str] = []
    for src in (r.get("badges") or [], price_info.get("badges") or []):
        for raw_badge in src:
            text = _badge_text(deref(raw_badge))
            if text and text[:64] not in badges:
                badges.append(text[:64])
    only_left = None
    for block in r.get("blocks") or []:
        message = deref(deref(block).get("onlyXLeftMessage")).get("translation")
        if (only_left := only_left_of(message if isinstance(message, str) else None)) is not None:
            break
    sponsored = bool(r.get("showAdLabel")) or r.get("sponsoredListingData") not in (None, {})
    type_id = b.get("accommodationTypeId")
    return SearchCard(
        sponsored=sponsored,
        preferred=preferred,
        badges=tuple(badges),
        slug=slug,
        url=canonical_url(slug),
        name=str(deref(r.get("displayName")).get("text") or page_name)[:300],
        external_id=str(b["id"]) if b.get("id") else None,
        review_score=score.quantize(Decimal("0.1")) if score and count else None,
        review_count=count or None,
        stars=stars if stars else None,
        address=loc.get("address"),
        city=(str(loc["city"])[:120] if loc.get("city") else None),
        district=district_of(shown.get("displayLocation")),
        distance_text=shown.get("mainDistance"),
        lat=float(lat) if lat is not None else None,
        lng=float(lng) if lng is not None else None,
        image_url=f"{IMAGE_HOST}{photo}"
        if isinstance(photo, str) and photo.startswith("/")
        else None,
        price=price,
        currency=currency,
        sold_out=bool(deref(r.get("soldOutInfo")).get("isSoldOut")),
        type_id=int(type_id) if type_id else None,
        autoextended=bool(pers.get("autoextended")),
        only_left=only_left,
    )


def _facets(entry: dict[str, Any], deref: Deref) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw_group in entry.get("filters") or []:
        group = deref(raw_group)
        if group.get("field") in SKIP_FACET_GROUPS:
            continue
        for raw in group.get("options") or []:
            option = deref(raw)
            uid, count = option.get("urlId"), option.get("count")
            if isinstance(uid, str) and "=" in uid and isinstance(count, int):
                out.setdefault(uid, count)
    return out


def _histogram(entry: dict[str, Any], deref: Deref) -> PriceHistogram | None:
    """Histogram thanh ngân sách; toàn 0 (Booking đôi khi không tính) → None."""
    for raw_group in entry.get("filters") or []:
        group = deref(raw_group)
        if group.get("field") != "price":
            continue
        slider = deref(group.get("sliderOptions"))
        bars = [_int(b) for b in slider.get("histogram") or []]
        lo, hi = _decimal(slider.get("min")), _decimal(slider.get("max"))
        if not bars or None in bars or lo is None or hi is None or hi <= lo:
            return None
        if not any(bars):
            return None
        return PriceHistogram(min=lo, max=hi, bars=tuple(b or 0 for b in bars))
    return None


def parse_search_entry(
    entry: dict[str, Any], deref: Deref, source: str, offset: int | None = None
) -> SearchPage:
    meta = deref(entry.get("searchMeta"))
    info = deref(meta.get("availabilityInfo"))
    pagination = deref(entry.get("pagination"))
    extended = _int(info.get("totalAutoextendedAvailable"))
    total = _int(info.get("totalAvailableNotAutoextended"))
    if total is None and (all_results := _int(pagination.get("nbResultsTotal"))) is not None:
        total = max(0, all_results - (extended or 0))  # tổng kênh báo gồm cả phần nới thêm
    checkin_raw = deref(meta.get("dates")).get("checkin")
    try:
        checkin = date.fromisoformat(checkin_raw) if checkin_raw else None
    except ValueError:
        checkin = None
    results = entry.get("results") or []
    every = [c for raw in results if (c := _card(raw, deref)) is not None]
    cards = [c for c in every if not c.autoextended]
    autoextended = extended
    per_page = _int(pagination.get("nbResultsPerPage"))
    low = info.get("hasLowAvailability")
    return SearchPage(
        total=total,
        checkin=checkin,
        cards=cards,
        source=source,
        per_page=per_page or None,
        offset=offset,
        facets=_facets(entry, deref),
        autoextended=autoextended if autoextended is not None else len(every) - len(cards),
        low_availability=low if isinstance(low, bool) else None,
        unavailability_pct=_int(info.get("unavailabilityPercent")),
        histogram=_histogram(entry, deref),
        rooms=_int(meta.get("nbRooms")),
        adults=_int(meta.get("nbAdults")),
        raw_count=len(results),
    )


# ---- Kho Apollo ----


def _search_entry(store: dict[str, Any]) -> tuple[dict[str, Any], int | None] | None:
    """(kết quả tìm kiếm, offset trong tham số truy vấn) từ khoá dạng `search({"input":…})`."""
    queries = (store.get("ROOT_QUERY") or {}).get("searchQueries") or {}
    for key, value in queries.items():
        if key.startswith("search(") and isinstance(value, dict) and "results" in value:
            try:
                args = json.loads(key[len("search(") : -1])
                offset = args["input"]["pagination"]["offset"]
            except (json.JSONDecodeError, KeyError, TypeError):
                offset = None
            return value, int(offset) if isinstance(offset, int) else None
    return None


def _from_apollo(html: str) -> SearchPage | None:
    m = _APOLLO_RE.search(html)
    if m is None:
        return None
    try:
        store = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    found = _search_entry(store) if isinstance(store, dict) else None
    if found is None:
        return None
    entry, offset = found
    return parse_search_entry(entry, store_deref(store), "apollo", offset)


# ---- Thẻ HTML (dự phòng) ----


def _text(node: Node | None) -> str | None:
    if node is None:
        return None
    text = " ".join(node.text(separator=" ").replace("\xa0", " ").split())
    return text or None


def _html_price(card: Node) -> tuple[Decimal | None, str | None]:
    m = _MONEY_RE.search(_text(card.css_first('[data-testid="price-and-discounted-price"]')) or "")
    if m is None:
        return None, None
    currency, amount = m.group(1), Decimal(m.group(2).replace(",", ""))
    taxes = _text(card.css_first('[data-testid="taxes-and-charges"]')) or ""
    extra = _MONEY_RE.search(taxes) if taxes.startswith("+") else None
    if extra is not None and extra.group(1) == currency:
        amount += Decimal(extra.group(2).replace(",", ""))
    return _money(amount, currency), currency


def _html_card(card: Node) -> SearchCard | None:
    link = card.css_first('a[data-testid="title-link"]')
    href = link.attributes.get("href") if link is not None else None
    try:
        ref = parse_url(href) if href else None
    except UnsupportedUrl:
        ref = None
    if ref is None:
        return None
    review = _text(card.css_first('[data-testid="review-score"]')) or ""
    score, count = _SCORE_RE.search(review), _REVIEWS_RE.search(review)
    rating = card.css_first('button[aria-label*="out of 5"]')
    stars = _STARS_RE.search(rating.attributes.get("aria-label") or "") if rating else None
    image = card.css_first('img[data-testid="image"]')
    price, currency = _html_price(card)
    return SearchCard(
        slug=ref.listing_key,
        url=ref.url,
        name=(_text(card.css_first('[data-testid="title"]')) or ref.listing_key)[:300],
        review_score=Decimal(score.group(1)) if score else None,
        review_count=int(count.group(1).replace(",", "")) if count else None,
        stars=Decimal(stars.group(1)) if stars else None,
        district=district_of(_text(card.css_first('[data-testid="address-link"]'))),
        distance_text=_text(card.css_first('[data-testid="distance"]')),
        image_url=image.attributes.get("src") if image is not None else None,
        price=price,
        currency=currency,
    )


def _from_html(html: str) -> SearchPage:
    tree = HTMLParser(html)
    total = None
    for h1 in tree.css("h1"):
        m = _FOUND_RE.search(_text(h1) or "")
        if m:
            total = int(re.sub(r"[^\d]", "", m.group(1)))
            break
    cards = [
        c
        for node in tree.css('[data-testid="property-card"]')
        if (c := _html_card(node)) is not None
    ]
    return SearchPage(total=total, checkin=None, cards=cards, source="html")


def parse_search_page(html: str) -> SearchPage:
    page = _from_apollo(html)
    # Kho Apollo nói khu vực hết chỗ hoặc chỉ có thẻ nới thêm: thẻ HTML (không phân biệt nới thêm)
    # không được dùng thay.
    if page is not None and (page.cards or page.total == 0 or (page.autoextended or 0) > 0):
        return page
    fallback = _from_html(html)
    if page is None:
        return fallback
    if not fallback.cards:
        return page
    # Kho Apollo không có thẻ (đổi cấu trúc?) nhưng HTML có: lấy thẻ HTML, giữ phần còn lại của kho.
    return SearchPage(
        total=page.total if page.total is not None else fallback.total,
        checkin=page.checkin,
        cards=fallback.cards,
        source="html",
        per_page=page.per_page,
        offset=page.offset,
        facets=page.facets,
        autoextended=page.autoextended,
        low_availability=page.low_availability,
        unavailability_pct=page.unavailability_pct,
        histogram=page.histogram,
        rooms=page.rooms,
        adults=page.adults,
    )
