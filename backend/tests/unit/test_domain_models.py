from decimal import Decimal

from app.domain.models import RatePlan, RoomOffer


def _offer(*rates: RatePlan) -> RoomOffer:
    return RoomOffer(
        booking_room_id="123",
        name="Deluxe",
        max_occupancy=2,
        badge_count=None,
        dropdown_max=5,
        rates=tuple(rates),
    )


def test_min_price_and_min_refundable_price() -> None:
    offer = _offer(
        RatePlan(name="Non-refundable", price=Decimal("100"), currency="VND", refundable=False, breakfast=False),
        RatePlan(name="Flexible", price=Decimal("120"), currency="VND", refundable=True, breakfast=False),
        RatePlan(name="Flex+BF", price=Decimal("140"), currency="VND", refundable=True, breakfast=True),
    )
    assert offer.min_price == Decimal("100")
    assert offer.min_refundable_price == Decimal("120")
    assert offer.currency == "VND"


def test_min_prices_when_no_rates() -> None:
    offer = _offer()
    assert offer.min_price is None
    assert offer.min_refundable_price is None
    assert offer.currency is None
