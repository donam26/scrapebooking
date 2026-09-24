import pytest

from app.domain.models import StockConfidence
from app.domain.stock import derive_stock


@pytest.mark.parametrize(
    "badge,dropdown,cap,rooms_left,confidence",
    [
        (3, 3, 10, 3, StockConfidence.EXACT),
        (1, None, 10, 1, StockConfidence.EXACT),
        (None, 10, 10, 10, StockConfidence.CAPPED),
        (None, 12, 10, 12, StockConfidence.CAPPED),
        (None, 4, 10, None, StockConfidence.HIDDEN),
        (None, None, 10, None, StockConfidence.HIDDEN),
        (0, 0, 10, 0, StockConfidence.SOLD_OUT),
        (None, 0, 10, 0, StockConfidence.SOLD_OUT),
    ],
)
def test_derive_stock(badge, dropdown, cap, rooms_left, confidence) -> None:  # type: ignore[no-untyped-def]
    stock = derive_stock(badge_count=badge, dropdown_max=dropdown, page_cap=cap)
    assert stock.rooms_left == rooms_left
    assert stock.confidence == confidence


def test_badge_wins_over_dropdown_when_both_present() -> None:
    stock = derive_stock(badge_count=2, dropdown_max=10, page_cap=10)
    assert stock.rooms_left == 2
    assert stock.confidence == StockConfidence.EXACT
