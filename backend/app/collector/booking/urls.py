"""URL Booking.com (thuần): nhận diện trang khách sạn, dựng URL probe."""

import re
from datetime import date, timedelta
from urllib.parse import urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches
from app.domain.models import ListingRef

_PATH_RE = re.compile(
    r"^/hotel/(?P<cc>[a-z]{2})/(?P<name>[a-z0-9\-]+?)(?:\.[a-z]{2}(?:-[a-z]{2})?)?\.html$"
)


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "booking.com"):
        return None
    m = _PATH_RE.match(urlparse(url.strip()).path)
    if not m:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="Booking",
            example="booking.com/hotel/vn/ten-khach-san.html",
        )
    slug = f"{m.group('cc')}/{m.group('name')}"
    return ListingUrl(
        channel="booking",
        listing_key=slug,
        url=canonical_url(slug),
        country_code=m.group("cc"),
    )


def canonical_url(slug: str) -> str:
    return f"https://www.booking.com/hotel/{slug}.html"


def pagename(listing: ListingRef) -> str:
    """Phần tên trong slug "vn/the-reverie-saigon" (biến `pagename` của GraphQL Booking)."""
    return listing.listing_key.split("/", 1)[1]


def build_hotel_url(
    listing: ListingRef, checkin: date, nights: int, adults: int, currency: str
) -> str:
    checkout = checkin + timedelta(days=nights)
    return (
        f"https://www.booking.com/hotel/{listing.listing_key}.en-gb.html"
        f"?checkin={checkin.isoformat()}&checkout={checkout.isoformat()}"
        f"&group_adults={adults}&no_rooms=1&group_children=0"
        f"&selected_currency={currency}&lang=en-gb"
    )
