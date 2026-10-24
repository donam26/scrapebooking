"""Truy vấn GraphQL `FullSearch` của trang kết quả Booking.com (thuần): dựng request, đọc phản hồi.

Kiểm live 16/10/2026 (`tests/fixtures/booking/fullsearch_vungtau_hotels_2026-11-18.json`):
- cùng endpoint `/dml/graphql` và csrf với lịch (`collector/booking/calendar.py`); query tối giản
  được chấp nhận;
- `pagination.rowsPerPage` tối đa 100 (gửi 250 → 100); `rowsPerPage = 1` chỉ để lấy số đếm, facet;
- trong một phiên đổi được khu vực (`location`: CITY/DISTRICT/REGION/LANDMARK/LATLONG), ngày, bộ lọc
  (`filters.selectedFilters` = chuỗi `nflt`, các lựa chọn cùng nhóm là OR), số phòng/người lớn;
- `nbRooms`, `nbAdults` bị kẹp ≤ 30; Booking chỉ trả tối đa 1.000 kết quả mỗi truy vấn (số đếm và
  facet thì không bị cắt);
- `sorters.selectedSorter = "price"` ổn định khi lật trang; để `None` là thứ tự "phổ biến".
"""

import json
import secrets
from datetime import date, timedelta
from typing import Any

from app.marketscan.parser import SearchPage, parse_search_entry, plain

MAX_ROWS = 100
RESULT_CAP = 1000
MAX_GROUP = 30  # nbRooms / nbAdults tối đa kênh nhận
RADII = (1000, 3000, 5000)  # lựa chọn của bộ lọc `distance` (m)

SEARCH_QUERY = """query FullSearch($input: SearchQueryInput!) {
  searchQueries {
    search(input: $input) {
      ... on SearchQueryOutput {
        pagination { nbResultsPerPage nbResultsTotal }
        searchMeta {
          availabilityInfo {
            hasLowAvailability unavailabilityPercent
            totalAvailableNotAutoextended totalAutoextendedAvailable
          }
          dates { checkin checkout }
          nbRooms
          nbAdults
        }
        filters { field options { urlId count } sliderOptions { min max histogram } }
        results {
          basicPropertyData {
            id
            pageName
            accommodationTypeId
            location { address city countryCode latitude longitude }
            reviews { reviewsCount totalScore }
            starRating { value }
            photos { main { highResJpegUrl { relativeUrl } } }
          }
          displayName { text }
          location { displayLocation mainDistance }
          priceDisplayInfoIrene {
            displayPrice { amountPerStay { amountUnformatted currency } }
            excludedCharges {
              excludeChargesAggregated { amountPerStay { amountUnformatted currency } }
            }
            badges { name { translation } }
          }
          blocks { onlyXLeftMessage { translation } }
          soldOutInfo { isSoldOut }
          persuasion { autoextended preferred preferredPlus }
          badges { caption { translation } }
          showAdLabel
          sponsoredListingData { id }
        }
      }
    }
  }
}
"""


class SearchSchemaError(RuntimeError):
    """Kênh trả lỗi GraphQL (đổi schema, đầu vào sai…): không phải bị chặn, không thử lại."""


def search_location(
    dest_type: str, dest_id: str, lat: float | None = None, lng: float | None = None
) -> dict[str, Any]:
    """`location` của input: điểm toạ độ cho `latlong`, còn lại dest_id của Booking."""
    if dest_type == "latlong":
        if lat is None or lng is None:
            raise ValueError("latlong area needs lat/lng")
        return {"destType": "LATLONG", "latitude": float(lat), "longitude": float(lng)}
    return {"destType": dest_type.upper(), "destId": int(dest_id)}


def combine_nflt(*parts: str | None) -> str | None:
    """Ghép các đoạn `nflt` ("ht_id=204;class=4", "distance=3000"), bỏ trùng, giữ thứ tự."""
    out: list[str] = []
    for part in parts:
        for item in (part or "").split(";"):
            item = item.strip()
            if item and item not in out:
                out.append(item)
    return ";".join(out) or None


def radius_nflt(radius_m: int | None) -> str | None:
    return f"distance={radius_m}" if radius_m else None


def build_search_request(
    location: dict[str, Any],
    night: date,
    *,
    adults: int = 2,
    rooms: int = 1,
    nflt: str | None = None,
    rows: int = MAX_ROWS,
    offset: int = 0,
    sorter: str | None = None,
) -> dict[str, Any]:
    """1 đêm; `rooms` phòng cho `adults` người lớn (kẹp ≤ 30), không trẻ em. Input giữ đúng bộ khoá
    frontend Booking gửi (bắt 16/10/2026); `useSearchParamsFromSession = False` để phiên không áp
    bộ lọc/ngày của lần tìm trước."""
    checkin, checkout = night.isoformat(), (night + timedelta(days=1)).isoformat()
    input_: dict[str, Any] = {
        "acidCarouselContext": None,
        "childrenAges": [],
        "dates": {"checkin": checkin, "checkout": checkout},
        "doAvailabilityCheck": False,
        "encodedAutocompleteMeta": None,
        "enableCampaigns": True,
        "filters": {"selectedFilters": nflt} if nflt else {},
        "flexibleDatesConfig": {
            "broadDatesCalendar": {"checkinMonths": [], "los": [], "startWeekdays": []},
            "dateFlexUseCase": "DATE_RANGE",
            "dateRangeCalendar": {"checkin": [checkin], "checkout": [checkout]},
        },
        "forcedBlocks": None,
        "location": location,
        "metaContext": {
            "metaCampaignId": 0,
            "externalTotalPrice": None,
            "feedPrice": None,
            "hotelCenterAccountId": None,
            "rateRuleId": None,
            "dragongateTraceId": None,
            "pricingProductsTag": None,
        },
        "nbRooms": max(1, min(rooms, MAX_GROUP)),
        "nbAdults": max(1, min(adults, MAX_GROUP)),
        "nbChildren": 0,
        "showAparthotelAsHotel": True,
        "needsRoomsMatch": False,
        "optionalFeatures": {
            "businessPopularitySorter": True,
            "forceArpExperiments": True,
            "testProperties": False,
        },
        "pagination": {"rowsPerPage": max(1, min(rows, MAX_ROWS)), "offset": max(0, offset)},
        "rawQueryForSession": None,
        "referrerBlock": None,
        "sbCalendarOpen": False,
        "sorters": {"selectedSorter": sorter, "referenceGeoId": None, "tripTypeIntentId": None},
        "travelPurpose": 2,
        "seoThemeIds": [],
        "useSearchParamsFromSession": False,
        "merchInput": {"testCampaignIds": []},
        "webSearchContext": {
            "reason": "CLIENT_SIDE_UPDATE",
            "source": "SEARCH_RESULTS",
            "outcome": "SEARCH_RESULTS",
        },
        "clientSideRequestId": secrets.token_hex(8),
        "searchSource": {"backendSource": "UNSPECIFIED"},
    }
    return {
        "operationName": "FullSearch",
        "variables": {"input": input_},
        "extensions": {},
        "query": SEARCH_QUERY,
    }


def search_headers(csrf_token: str | None, referer: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Origin": "https://www.booking.com",
        "Referer": referer,
        "apollographql-client-name": "b-search-web-searchresults",
        "x-booking-context-action-name": "searchresults_irene",
        "x-booking-csrf-token": csrf_token or "",
        "x-booking-site-type-id": "1",
        "x-booking-topic": "capla_browser_b-search-web-searchresults",
    }


def parse_search_response(text: str, offset: int | None = None) -> SearchPage:
    """JSON `FullSearch` → `SearchPage`. Lỗi GraphQL/JSON hỏng → `SearchSchemaError`."""
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SearchSchemaError(f"invalid json: {exc.msg}") from exc
    data = body.get("data") if isinstance(body, dict) else None
    entry = plain(plain(plain(data).get("searchQueries")).get("search"))
    if not entry or "results" not in entry:
        errors = body.get("errors") if isinstance(body, dict) else None
        raise SearchSchemaError(f"no search result: {json.dumps(errors)[:300] if errors else ''}")
    return parse_search_entry(entry, plain, "graphql", offset)
