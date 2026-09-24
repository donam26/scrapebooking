import json
from pathlib import Path

import pytest

from app.collector.booking.parser import page_to_dict, parse_hotel_page
from app.domain.models import PageOutcome

FIXTURES = ["available_with_badge", "available_no_badge", "sold_out"]


def _load(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / "html" / f"{name}.html").read_text(encoding="utf-8")


def test_available_with_badge_has_exact_room(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "available_with_badge"), expected_currency="VND")
    assert page.outcome == PageOutcome.ROOMS
    assert page.booking_hotel_id and page.booking_hotel_id.isdigit()
    assert page.hotel_name
    assert page.csrf_token
    assert len(page.offers) >= 1
    assert any(o.badge_count is not None and o.badge_count >= 1 for o in page.offers)
    for offer in page.offers:
        assert offer.booking_room_id
        assert offer.name
        assert len(offer.rates) >= 1
        assert all(r.price > 0 and r.currency == "VND" for r in offer.rates)


def test_available_no_badge_has_dropdowns(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "available_no_badge"), expected_currency="VND")
    assert page.outcome == PageOutcome.ROOMS
    assert all(o.dropdown_max is not None and o.dropdown_max >= 1 for o in page.offers)


def test_sold_out_page(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "sold_out"), expected_currency="VND")
    assert page.outcome == PageOutcome.SOLD_OUT
    assert page.offers == ()


def test_empty_html_is_empty_outcome() -> None:
    page = parse_hotel_page("<html><body></body></html>", expected_currency="VND")
    assert page.outcome == PageOutcome.EMPTY


def test_rate_plan_grouping_by_room_type(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "available_with_badge"), expected_currency="VND")
    by_id = {o.booking_room_id: o for o in page.offers}
    deluxe = by_id["12345601"]
    assert deluxe.name == "Deluxe Room"
    assert deluxe.max_occupancy == 2
    assert deluxe.badge_count == 2
    assert deluxe.dropdown_max == 2
    assert [(r.name, str(r.price), r.refundable, r.breakfast) for r in deluxe.rates] == [
        ("Non-refundable", "2450000", False, None),
        ("Free cancellation + breakfast", "2890000", True, True),
    ]
    assert deluxe.min_price == deluxe.rates[0].price
    assert deluxe.min_refundable_price == deluxe.rates[1].price
    suite = by_id["12345603"]
    assert suite.badge_count is None and suite.dropdown_max == 10


@pytest.mark.parametrize("name", FIXTURES)
def test_golden(fixtures_dir: Path, name: str) -> None:
    expected_path = fixtures_dir / "html" / f"{name}.expected.json"
    page = parse_hotel_page(_load(fixtures_dir, name), expected_currency="VND")
    assert page_to_dict(page) == json.loads(expected_path.read_text(encoding="utf-8"))
