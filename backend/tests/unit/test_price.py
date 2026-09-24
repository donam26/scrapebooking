from decimal import Decimal

import pytest

from app.collector.booking.parser import parse_price


@pytest.mark.parametrize(
    "text,fallback,price,currency",
    [
        ("VND 3,450,000", "VND", Decimal("3450000"), "VND"),
        ("VND\xa03.450.000", "VND", Decimal("3450000"), "VND"),
        ("US$120", "USD", Decimal("120"), "USD"),
        ("€ 1,234.50", "EUR", Decimal("1234.50"), "EUR"),
        ("₫ 950,000", "VND", Decimal("950000"), "VND"),
        ("Price 2,500", "THB", Decimal("2500"), "THB"),
        ("1.234,56 zł", "PLN", Decimal("1234.56"), "PLN"),
    ],
)
def test_parse_price(text: str, fallback: str, price: Decimal, currency: str) -> None:
    assert parse_price(text, fallback_currency=fallback) == (price, currency)


def test_parse_price_no_number() -> None:
    assert parse_price("Sold out", fallback_currency="VND") is None
