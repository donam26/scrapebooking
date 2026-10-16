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
        # Dropdown dưới trần là số phòng còn thật (dữ liệu thật: badge = dropdown 100% khi có cả
        # hai; 8–9 không có badge nhưng vẫn là số thật).
        (None, 4, 10, 4, StockConfidence.EXACT),
        (None, 8, 10, 8, StockConfidence.EXACT),
        (None, 9, 10, 9, StockConfidence.EXACT),
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


def test_listing_cap_below_page_cap_makes_its_max_a_floor() -> None:
    # Park Hyatt Saigon: dropdown chưa bao giờ quá 9 (43% quan sát dồn ở 9) → 9 là trần riêng.
    nine = derive_stock(badge_count=None, dropdown_max=9, page_cap=10, listing_cap=9)
    assert (nine.rooms_left, nine.confidence) == (9, StockConfidence.CAPPED)
    eight = derive_stock(badge_count=None, dropdown_max=8, page_cap=10, listing_cap=9)
    assert (eight.rooms_left, eight.confidence) == (8, StockConfidence.EXACT)


def test_listing_cap_never_raises_the_page_cap() -> None:
    stock = derive_stock(badge_count=None, dropdown_max=10, page_cap=10, listing_cap=12)
    assert (stock.rooms_left, stock.confidence) == (10, StockConfidence.CAPPED)


def test_badge_is_exact_even_at_the_listing_cap() -> None:
    stock = derive_stock(badge_count=7, dropdown_max=7, page_cap=10, listing_cap=7)
    assert (stock.rooms_left, stock.confidence) == (7, StockConfidence.EXACT)


def test_rate_scope_signals_are_only_lower_bounds() -> None:
    # "Chỉ còn 1 phòng có giá này": loại phòng còn ít nhất bấy nhiêu, không phải số chính xác.
    stock = derive_stock(badge_count=1, dropdown_max=None, page_cap=10, scope="rate")
    assert (stock.rooms_left, stock.confidence) == (1, StockConfidence.CAPPED)
    assert derive_stock(0, None, 10, scope="rate").confidence == StockConfidence.SOLD_OUT
    assert derive_stock(1, None, 10, scope="room_type").confidence == StockConfidence.EXACT
    by_rate = derive_stock(None, 4, 10, scope="rate")
    assert (by_rate.rooms_left, by_rate.confidence) == (4, StockConfidence.CAPPED)
