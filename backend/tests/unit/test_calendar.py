import json
from datetime import date

from app.collector.booking.calendar import (
    GRAPHQL_URL,
    build_calendar_request,
    calendar_headers,
    parse_calendar_response,
)


def test_build_request_shape() -> None:
    req = build_calendar_request("the-reverie-saigon", date(2026, 10, 1), 30, adults=2)
    assert req["operationName"] == "AvailabilityCalendar"
    cfg = req["variables"]["input"]["searchConfig"]
    assert cfg["searchConfigDate"] == {"startDate": "2026-10-01", "amountOfDays": 30}
    assert cfg["nbAdults"] == 2
    assert cfg["nbRooms"] == 1
    assert req["variables"]["input"]["pagename"] == "the-reverie-saigon"
    assert "availabilityCalendar(input: $input)" in req["query"]
    assert GRAPHQL_URL.startswith("https://www.booking.com/dml/graphql")


def test_headers_include_csrf_and_referer() -> None:
    h = calendar_headers("tok", referer="https://www.booking.com/hotel/vn/x.html")
    assert h["x-booking-csrf-token"] == "tok"
    assert h["Referer"] == "https://www.booking.com/hotel/vn/x.html"
    assert h["x-booking-site-type-id"] == "1"


def test_parse_success() -> None:
    body = {
        "data": {
            "availabilityCalendar": {
                "hotelId": 123,
                "days": [
                    {
                        "checkin": "2026-10-01",
                        "available": True,
                        "minLengthOfStay": 1,
                        "avgPriceFormatted": "VND 3,000,000",
                    },
                    {
                        "checkin": "2026-10-02",
                        "available": False,
                        "minLengthOfStay": 0,
                        "avgPriceFormatted": None,
                    },
                    {
                        "checkin": "2026-10-03",
                        "available": True,
                        "minLengthOfStay": 2,
                        "avgPriceFormatted": "VND 2,500,000",
                    },
                ],
            }
        }
    }
    res = parse_calendar_response(json.dumps(body))
    assert res.ok
    assert len(res.days) == 3
    d1 = res.day(date(2026, 10, 1))
    assert d1 and d1.available and d1.min_length_of_stay == 1
    d2 = res.day(date(2026, 10, 2))
    assert d2 and not d2.available and d2.min_length_of_stay == 1
    d3 = res.day(date(2026, 10, 3))
    assert d3 and d3.min_length_of_stay == 2 and d3.avg_price_display == "VND 2,500,000"


def test_parse_error_payload() -> None:
    body = {"data": {"availabilityCalendar": {"message": "Hotel not found"}}}
    res = parse_calendar_response(json.dumps(body))
    assert not res.ok
    assert res.error == "Hotel not found"


def test_parse_garbage() -> None:
    res = parse_calendar_response("<html>challenge</html>")
    assert not res.ok
    assert res.error and "json" in res.error.lower()
