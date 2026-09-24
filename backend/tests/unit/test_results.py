from datetime import date
from decimal import Decimal

from app.collector.booking.results import probe_result_from_page
from app.domain.models import (
    PageOutcome,
    ParsedPage,
    ProbeMethod,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)


def _page(outcome: PageOutcome, offers: tuple[RoomOffer, ...] = ()) -> ParsedPage:
    return ParsedPage(outcome, "111", "Hotel X", "csrf", offers)


def test_rooms_outcome_maps_to_ok() -> None:
    offer = RoomOffer(
        "1", "Deluxe", 2, None, 5, (RatePlan("Standard", Decimal("10"), "VND", None, None),)
    )
    r = probe_result_from_page(
        _page(PageOutcome.ROOMS, (offer,)),
        method=ProbeMethod.HTTP,
        checkin=date(2026, 10, 1),
        nights=1,
        adults=2,
        raw_html="<html/>",
        http_status=200,
        session_id="s",
        duration_ms=5,
    )
    assert r.status == ProbeStatus.OK
    assert r.checkout == date(2026, 10, 2)
    assert r.offers == (offer,)
    assert r.booking_hotel_id == "111"
    assert r.hotel_name == "Hotel X"


def test_sold_out_and_empty_mapping() -> None:
    kw = dict(
        method=ProbeMethod.BROWSER,
        checkin=date(2026, 10, 1),
        nights=2,
        adults=2,
        raw_html="",
        http_status=None,
        session_id=None,
        duration_ms=0,
    )
    assert probe_result_from_page(_page(PageOutcome.SOLD_OUT), **kw).status == ProbeStatus.SOLD_OUT  # type: ignore[arg-type]
    assert probe_result_from_page(_page(PageOutcome.EMPTY), **kw).status == ProbeStatus.NO_ROOMS_1N  # type: ignore[arg-type]
