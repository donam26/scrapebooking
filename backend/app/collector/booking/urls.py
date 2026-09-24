from datetime import date, timedelta

from app.domain.models import HotelRef

COUNTRY_CURRENCY: dict[str, str] = {
    "vn": "VND", "th": "THB", "sg": "SGD", "my": "MYR", "id": "IDR", "ph": "PHP",
    "kh": "USD", "la": "USD", "jp": "JPY", "kr": "KRW", "cn": "CNY", "hk": "HKD",
    "tw": "TWD", "au": "AUD", "nz": "NZD", "us": "USD", "ca": "CAD", "gb": "GBP",
    "fr": "EUR", "de": "EUR", "it": "EUR", "es": "EUR", "nl": "EUR", "pt": "EUR",
    "ae": "AED", "in": "INR",
}  # fmt: skip


def currency_for(country_code: str) -> str:
    return COUNTRY_CURRENCY.get(country_code.lower(), "USD")


def build_hotel_url(hotel: HotelRef, checkin: date, nights: int, adults: int, currency: str) -> str:
    checkout = checkin + timedelta(days=nights)
    return (
        f"https://www.booking.com/hotel/{hotel.slug}.en-gb.html"
        f"?checkin={checkin.isoformat()}&checkout={checkout.isoformat()}"
        f"&group_adults={adults}&no_rooms=1&group_children=0"
        f"&selected_currency={currency}&lang=en-gb"
    )
