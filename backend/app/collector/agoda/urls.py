"""URL Agoda (thuần): nhận diện trang khách sạn, dựng URL/payload các API JSON."""

import base64
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches
from app.domain.models import ListingRef

BASE = "https://www.agoda.com"
LOCALE = "vi-vn"
ROOM_GRID_PATH = "/api/v1/property/room-grid"
# Khoá public của web Agoda (header ag-initiator-api-key), không phải bí mật của tài khoản.
INITIATOR_API_KEY = "b3949fd5-9553-4b4e-b221-48be2a1b84a8"
CURRENCY_IDS = {"VND": 78}

# /vi-vn/<slug>/hotel/<thành-phố>.html, tiền tố ngôn ngữ tuỳ chọn (bản tiếng Anh không có).
_PATH_RE = re.compile(
    r"^/(?:[a-z]{2}-[a-z]{2}/)?(?P<slug>[a-z0-9][a-z0-9_\-]*)/hotel/(?P<city>[a-z0-9_\-]+)\.html$"
)
_COUNTRY_RE = re.compile(r"-(?P<cc>[a-z]{2})$")  # "phu-quoc-island-vn" -> "vn"
_ID_PARAMS = ("selectedproperty", "hotel_id", "hid", "hotel")
_ID_KEY = "id/"  # listing_key của URL chỉ có propertyId (trang tìm kiếm, link đối tác)


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "agoda.com"):
        return None
    parsed = urlparse(url.strip())
    query = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
    property_id = next(
        (query[p][0] for p in _ID_PARAMS if p in query and query[p][0].isdigit()), None
    )
    m = _PATH_RE.match(parsed.path.lower())
    if m:
        key = f"{m.group('slug')}/hotel/{m.group('city')}"
        cc = _COUNTRY_RE.search(m.group("city"))
        return ListingUrl(
            channel="agoda",
            listing_key=key,
            url=canonical_url(key),
            country_code=cc.group("cc") if cc else None,
            external_id=property_id,
        )
    if property_id is not None:
        return ListingUrl(
            channel="agoda",
            listing_key=_ID_KEY + property_id,
            url=f"{BASE}/{LOCALE}/search?selectedproperty={property_id}",
            external_id=property_id,
        )
    raise UnsupportedUrl(
        "not_hotel_page",
        channel="Agoda",
        example="agoda.com/vi-vn/ten-khach-san/hotel/thanh-pho-vn.html",
    )


def canonical_url(listing_key: str) -> str:
    return f"{BASE}/{LOCALE}/{listing_key}.html"


def property_id(listing: ListingRef) -> str | None:
    """propertyId biết được mà không cần gọi mạng (đã verify, hoặc URL dạng ?selectedproperty=)."""
    if listing.external_id:
        return listing.external_id
    if listing.listing_key.startswith(_ID_KEY):
        return listing.listing_key.removeprefix(_ID_KEY)
    return None


def secondary_data_url(
    property_id: str,
    checkin: date | None = None,
    nights: int = 1,
    adults: int = 2,
    currency: str = "VND",
) -> str:
    """API dữ liệu trang khách sạn (bảng phòng + thông tin). Không kèm ngày: chỉ thông tin, nhẹ
    hơn. `price_view=2`: giá hiển thị gồm thuế phí theo phòng/đêm. Tiền tệ thật do header
    cr-currency-code quyết định, không phải tham số URL."""
    url = f"{BASE}/api/cronos/property/BelowFoldParams/GetSecondaryData?"
    if checkin is not None:
        url += (
            f"checkIn={checkin.isoformat()}&los={nights}&rooms=1&adults={adults}&children=0"
            f"&currencyCode={currency}&"
        )
    return url + (
        f"hotel_id={property_id}&all=false&isHostPropertiesEnabled=true&price_view=2&pagetypeid=7"
    )


def suggest_url(text: str) -> str:
    return (
        f"{BASE}/api/cronos/search/GetUnifiedSuggestResult/3/24/24/0/{LOCALE}/"
        f"?searchText={quote(text)}&origin=VN&cid=-1&pageTypeId=1&logtime=1&isHotelLandSearch=true"
    )


def room_grid_request(
    property_id: str, checkin: date, nights: int, adults: int, currency: str
) -> dict[str, Any]:
    """Payload tối thiểu của API room-grid (chỉ dùng để xác nhận `isSoldOut`)."""
    return {
        "pageSessionId": "",
        "clientApplicationName": "capybara",
        "pricingRequest": {"attributionModels": [{"modelId": 32, "cid": -1}]},
        "userContext": {
            "priceStrategy": 101,
            "firstDownloadVersion": "6_0",
            "cmsMode": 0,
            "currencyDisplayType": 2,
            "currencyId": CURRENCY_IDS.get(currency, CURRENCY_IDS["VND"]),
            "mseHotelIds": [],
            "pointsMaxId": 0,
        },
        "userState": {"currentFunnel": "regular", "loyalty": {"pastBookingsLevel": -1}},
        "propertyId": property_id,
        "fields": [],
        "supportFeatures": [],
        "searchCriteria": {
            "adults": adults,
            "checkIn": checkin.isoformat(),
            "checkOut": (checkin + timedelta(days=nights)).isoformat(),
            "childrenAges": [],
            "durationType": "nightly",
            "rooms": 1,
        },
        "searchFilters": {"filters": "", "syncIds": []},
        "toggles": {},
    }


def gate_meta(now_ms: int, user_id: str, path: str = ROOM_GRID_PATH) -> str:
    """Header x-gate-meta của web Agoda: base64("<ms>|<ag-user-id>|<path>")."""
    return base64.b64encode(f"{now_ms}|{user_id}|{path}".encode()).decode()
