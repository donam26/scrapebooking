import json
from datetime import date
from typing import Any

from app.domain.models import CalendarDay, CalendarResult

GRAPHQL_URL = "https://www.booking.com/dml/graphql?lang=en-gb"

CALENDAR_QUERY = (
    "query AvailabilityCalendar($input: AvailabilityCalendarQueryInput!) {\n"
    "  availabilityCalendar(input: $input) {\n"
    "    ... on AvailabilityCalendarQueryResult {\n"
    "      hotelId\n"
    "      days { available avgPriceFormatted checkin minLengthOfStay __typename }\n"
    "      __typename\n"
    "    }\n"
    "    ... on AvailabilityCalendarQueryError { message __typename }\n"
    "    __typename\n"
    "  }\n"
    "}\n"
)


def build_calendar_request(pagename: str, start: date, days: int, adults: int) -> dict[str, Any]:
    return {
        "operationName": "AvailabilityCalendar",
        "variables": {
            "input": {
                "travelPurpose": 2,
                "pagename": pagename,
                "searchConfig": {
                    "searchConfigDate": {"startDate": start.isoformat(), "amountOfDays": days},
                    "nbAdults": adults,
                    "nbRooms": 1,
                },
            }
        },
        "extensions": {},
        "query": CALENDAR_QUERY,
    }


def calendar_headers(csrf_token: str | None, referer: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Origin": "https://www.booking.com",
        "Referer": referer,
        "x-booking-context-action-name": "hotel",
        "x-booking-csrf-token": csrf_token or "",
        "x-booking-site-type-id": "1",
        "x-booking-topic": "capla_browser_b-property-web-property-page",
    }


def parse_calendar_response(text: str) -> CalendarResult:
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return CalendarResult(ok=False, error=f"invalid json: {exc.msg}")
    node = (body.get("data") or {}).get("availabilityCalendar") if isinstance(body, dict) else None
    if not isinstance(node, dict):
        errors = body.get("errors") if isinstance(body, dict) else None
        return CalendarResult(ok=False, error=f"unexpected payload: {errors or text[:200]}")
    if "days" not in node:
        return CalendarResult(ok=False, error=str(node.get("message") or "no days in payload"))
    days: list[CalendarDay] = []
    for d in node["days"]:
        try:
            checkin = date.fromisoformat(d["checkin"])
        except (KeyError, ValueError):
            continue
        mls = d.get("minLengthOfStay") or 1
        days.append(
            CalendarDay(
                checkin=checkin,
                available=bool(d.get("available")),
                min_length_of_stay=max(1, int(mls)),
                avg_price_display=d.get("avgPriceFormatted"),
            )
        )
    return CalendarResult(ok=True, days=tuple(days))
