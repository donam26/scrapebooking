"""GraphQL `FullSearch` của Booking: dựng request, đọc phản hồi thật (bắt live 16/10/2026).

Fixture: Vũng Tàu (city −3733750), lọc khách sạn (`ht_id=204`), đêm 2026-11-18, 2 người lớn, 4 kết
quả; chỉ giữ 8 nhóm facet. Histogram của lần bắt này toàn 0 (Booking có lúc không tính).
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.marketscan.graphql import (
    MAX_GROUP,
    MAX_ROWS,
    SearchSchemaError,
    build_search_request,
    combine_nflt,
    parse_search_response,
    radius_nflt,
    search_headers,
    search_location,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "booking"


@pytest.fixture(scope="module")
def body() -> str:
    return (FIXTURE / "fullsearch_vungtau_hotels_2026-11-18.json").read_text(encoding="utf-8")


def test_location_for_dest_and_latlong_areas() -> None:
    assert search_location("district", "2088") == {"destType": "DISTRICT", "destId": 2088}
    assert search_location("landmark", "258614") == {"destType": "LANDMARK", "destId": 258614}
    assert search_location("city", "-3733750") == {"destType": "CITY", "destId": -3733750}
    assert search_location("latlong", "10.77574,106.70141", 10.77574, 106.70141) == {
        "destType": "LATLONG",
        "latitude": 10.77574,
        "longitude": 106.70141,
    }
    with pytest.raises(ValueError):
        search_location("latlong", "x")


def test_nflt_combination_keeps_order_and_drops_duplicates() -> None:
    assert combine_nflt("ht_id=204;ht_id=206", radius_nflt(3000)) == (
        "ht_id=204;ht_id=206;distance=3000"
    )
    assert combine_nflt(None, None) is None and radius_nflt(None) is None
    assert combine_nflt("class=4", "class=4; ht_id=204") == "class=4;ht_id=204"


def test_request_shape_clamps_rows_rooms_and_adults() -> None:
    req = build_search_request(
        {"destType": "DISTRICT", "destId": 2088},
        date(2026, 12, 31),
        adults=50,
        rooms=40,
        nflt="ht_id=204",
        rows=250,
        offset=200,
        sorter="price",
    )
    assert req["operationName"] == "FullSearch" and "FullSearch(" in req["query"]
    inp = req["variables"]["input"]
    assert inp["dates"] == {"checkin": "2026-12-31", "checkout": "2027-01-01"}
    assert inp["flexibleDatesConfig"]["dateRangeCalendar"] == {
        "checkin": ["2026-12-31"],
        "checkout": ["2027-01-01"],
    }
    assert (inp["nbRooms"], inp["nbAdults"], inp["nbChildren"]) == (MAX_GROUP, MAX_GROUP, 0)
    assert inp["pagination"] == {"rowsPerPage": MAX_ROWS, "offset": 200}
    assert inp["filters"] == {"selectedFilters": "ht_id=204"}
    assert inp["sorters"]["selectedSorter"] == "price"
    assert inp["useSearchParamsFromSession"] is False and inp["rawQueryForSession"] is None
    plain = build_search_request({"destType": "CITY", "destId": 1}, date(2026, 11, 18), rows=0)
    pin = plain["variables"]["input"]
    assert pin["filters"] == {} and pin["pagination"] == {"rowsPerPage": 1, "offset": 0}
    assert pin["sorters"]["selectedSorter"] is None and (pin["nbRooms"], pin["nbAdults"]) == (1, 2)


def test_headers_carry_csrf_and_search_context() -> None:
    h = search_headers("tok", "https://www.booking.com/searchresults.en-gb.html")
    assert h["x-booking-csrf-token"] == "tok"
    assert h["x-booking-context-action-name"] == "searchresults_irene"
    assert h["Referer"].startswith("https://www.booking.com/searchresults")
    assert search_headers(None, "r")["x-booking-csrf-token"] == ""


def test_parse_real_fullsearch_response(body: str) -> None:
    page = parse_search_response(body, offset=0)
    assert page.source == "graphql" and page.offset == 0
    assert (page.total, page.autoextended, page.unavailability_pct) == (210, 0, 78)
    assert page.low_availability is False and page.checkin == date(2026, 11, 18)
    assert (page.rooms, page.adults, page.per_page) == (1, 2, 4)
    assert page.histogram is None  # toàn 0: coi như không có
    assert page.facets["class=4"] == 14 and page.facets["ht_id=213"] == 158
    assert page.facets["distance=3000"] == 200 and "oos=1" in page.facets
    assert [c.slug for c in page.cards] == [
        "vn/154-vung-tau",
        "vn/annata",
        "vn/the-imperial-vung-tau",
        "vn/khach-san-quoc-cuong-di-tam",
    ]
    first, imperial, last = page.cards[0], page.cards[2], page.cards[3]
    assert (first.name, first.external_id, first.type_id) == ("Bai Truoc Hotel", "1777952", 204)
    assert (first.price, first.currency, first.only_left) == (Decimal("279300"), "VND", 1)
    assert first.preferred == "preferred_plus" and first.sponsored is False
    assert (first.review_score, first.review_count, first.stars) == (Decimal("8.3"), 431, 2)
    assert first.image_url and first.image_url.startswith("https://cf.bstatic.com/xdata/")
    assert (imperial.stars, imperial.only_left, imperial.price) == (5, None, Decimal("2124252"))
    assert last.stars is None and last.only_left == 5 and last.city == "Thành phố Vũng Tàu"


def test_histogram_and_string_badges(body: str) -> None:
    data = json.loads(body)
    search = data["data"]["searchQueries"]["search"]
    price = next(f for f in search["filters"] if f["field"] == "price")
    price["sliderOptions"]["histogram"] = [0, 6, 100] + [0] * 47
    search["results"][0]["badges"] = [{"caption": {"translation": "Getaway Deal"}}]
    search["results"][1]["badges"] = [{"name": "Mobile-only price"}]
    page = parse_search_response(json.dumps(data))
    assert page.histogram is not None
    assert page.histogram.to_json() == {
        "min": 50000,
        "max": 2000000,
        "bars": [0, 6, 100] + [0] * 47,
    }
    assert page.cards[0].badges == ("Getaway Deal",)
    assert page.cards[1].badges == ("Mobile-only price",)


def test_graphql_errors_raise_schema_error() -> None:
    err = json.dumps({"errors": [{"message": 'Field "x" must have a selection'}], "data": None})
    with pytest.raises(SearchSchemaError, match="must have a selection"):
        parse_search_response(err)
    with pytest.raises(SearchSchemaError, match="invalid json"):
        parse_search_response("<html>challenge</html>")
