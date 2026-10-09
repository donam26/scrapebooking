"""Parser trang kết quả tìm kiếm Booking.com (thuần).

Nguồn chính: kho Apollo nhúng trong trang (`<script data-capla-store-data="apollo">`), có đủ id,
slug, toạ độ, điểm, số review, sao, ảnh, giá của từng thẻ. Dự phòng: thẻ HTML
`[data-testid=property-card]` khi trang không có kho này (thiếu id và toạ độ).
"""

import json
import re
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
IMAGE_HOST = "https://cf.bstatic.com"


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


@dataclass(frozen=True)
class SearchPage:
    total: int | None  # "N properties found": số chỗ ở còn phòng cho đêm đó
    checkin: date | None  # ngày nhận phòng trang thực sự hiển thị (None nếu không đọc được)
    cards: list[SearchCard]
    source: str  # apollo | html
    per_page: int | None = None  # kênh báo số thẻ mỗi trang (20/25, chế độ cuộn vô hạn 15)
    offset: int | None = None  # offset trang thực sự dùng (kênh có thể bỏ qua offset yêu cầu)
    # Số chỗ ở theo từng lựa chọn bộ lọc của truy vấn này: {"class=3": 315, "ht_id=204": 471…}.
    facets: dict[str, int] = field(default_factory=dict)


def _money(value: Decimal, currency: str) -> Decimal:
    step = Decimal("1") if currency == "VND" else Decimal("0.01")
    return value.quantize(step, rounding=ROUND_HALF_UP)


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def district_of(display_location: str | None) -> str | None:
    """ "District 1, Ho Chi Minh City" → "District 1"; chỉ có tên thành phố → None."""
    parts = [p.strip() for p in (display_location or "").split(",") if p.strip()]
    return parts[0][:120] if len(parts) >= 2 else None


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


def _apollo_price(info: dict[str, Any] | None) -> tuple[Decimal | None, str | None]:
    if not info:
        return None, None
    shown = (info.get("displayPrice") or {}).get("amountPerStay") or {}
    amount, currency = _decimal(shown.get("amountUnformatted")), shown.get("currency")
    if not amount or not currency:
        return None, None
    excluded = ((info.get("excludedCharges") or {}).get("excludeChargesAggregated") or {}).get(
        "amountPerStay"
    ) or {}
    extra = _decimal(excluded.get("amountUnformatted"))
    if extra and (excluded.get("currency") or currency) == currency:
        amount += extra
    return _money(amount, currency), str(currency)


def _deref(store: dict[str, Any], obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    ref = obj.get("__ref")
    return (store.get(ref) or {}) if isinstance(ref, str) else obj


def _facets(store: dict[str, Any], entry: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for group in entry.get("filters") or []:
        for raw in _deref(store, group).get("options") or []:
            option = _deref(store, raw)
            uid, count = option.get("urlId"), option.get("count")
            if isinstance(uid, str) and "=" in uid and isinstance(count, int):
                out.setdefault(uid, count)
    return out


def _apollo_card(store: dict[str, Any], raw: dict[str, Any]) -> SearchCard | None:
    r = _deref(store, raw)
    b = r.get("basicPropertyData") or {}
    loc = b.get("location") or {}
    page_name, cc = b.get("pageName"), str(loc.get("countryCode") or "").lower()
    if not page_name or len(cc) != 2:
        return None
    slug = f"{cc}/{page_name}"
    reviews = b.get("reviews") or {}
    count = int(reviews.get("reviewsCount") or 0)
    score = _decimal(reviews.get("totalScore"))
    stars = _decimal((b.get("starRating") or {}).get("value"))
    photo = (((b.get("photos") or {}).get("main") or {}).get("highResJpegUrl") or {}).get(
        "relativeUrl"
    )
    shown = r.get("location") or {}
    price, currency = _apollo_price(r.get("priceDisplayInfoIrene"))
    lat, lng = loc.get("latitude"), loc.get("longitude")
    pers = _deref(store, r.get("persuasion") or {})
    preferred = (
        "preferred_plus"
        if pers.get("preferredPlus")
        else "preferred"
        if pers.get("preferred")
        else None
    )
    badges: list[str] = []
    for src in (r.get("badges") or [], (r.get("priceDisplayInfoIrene") or {}).get("badges") or []):
        for b in src:
            name = ((_deref(store, b) or {}).get("name") or {}).get("translation")
            if isinstance(name, str) and name and name not in badges:
                badges.append(name[:64])
    sponsored = bool(r.get("showAdLabel")) or r.get("sponsoredListingData") not in (None, {})
    return SearchCard(
        sponsored=sponsored,
        preferred=preferred,
        badges=tuple(badges),
        slug=slug,
        url=canonical_url(slug),
        name=str((r.get("displayName") or {}).get("text") or page_name)[:300],
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
        sold_out=bool((r.get("soldOutInfo") or {}).get("isSoldOut")),
        type_id=int(b["accommodationTypeId"]) if b.get("accommodationTypeId") else None,
    )


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
    meta = entry.get("searchMeta") or {}
    pagination = entry.get("pagination") or {}
    total = pagination.get("nbResultsTotal")
    per_page = pagination.get("nbResultsPerPage")
    if total is None:
        total = (meta.get("availabilityInfo") or {}).get("totalAvailableNotAutoextended")
    checkin_raw = (meta.get("dates") or {}).get("checkin")
    try:
        checkin = date.fromisoformat(checkin_raw) if checkin_raw else None
    except ValueError:
        checkin = None
    cards = [
        c
        for raw in entry.get("results") or []
        if isinstance(raw, dict) and (c := _apollo_card(store, raw)) is not None
    ]
    return SearchPage(
        total=int(total) if total is not None else None,
        checkin=checkin,
        cards=cards,
        source="apollo",
        per_page=int(per_page) if per_page else None,
        offset=offset,
        facets=_facets(store, entry),
    )


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
    if page is not None and page.cards:
        return page
    fallback = _from_html(html)
    if page is None:
        return fallback
    # Kho Apollo không có thẻ (đổi cấu trúc?) nhưng HTML có: lấy thẻ HTML, giữ tổng/ngày của kho.
    return SearchPage(
        total=page.total if page.total is not None else fallback.total,
        checkin=page.checkin,
        cards=fallback.cards,
        source="html" if fallback.cards else "apollo",
        per_page=page.per_page,
        offset=page.offset,
        facets=page.facets,
    )
