"""URL Trip.com (thuần): nhận diện trang khách sạn, dựng URL probe."""

import re
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches
from app.domain.models import ListingRef

# /hotels/phu-quoc-island-hotel-detail-7047736/vinpearl-discovery-2-phu-quoc/
_SEO_PATH_RE = re.compile(r"/hotels/[a-z0-9\-]*hotel-detail-(?P<id>\d+)(?:/|$)", re.IGNORECASE)


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "trip.com"):
        return None
    hotel_id = _hotel_id(url.strip())
    if hotel_id is None:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="Trip.com",
            example="vn.trip.com/hotels/detail/?hotelId=123456",
        )
    return ListingUrl(
        channel="tripcom",
        listing_key=hotel_id,
        url=canonical_url(hotel_id),
        external_id=hotel_id,
    )


def _hotel_id(url: str) -> str | None:
    parsed = urlparse(url)
    m = _SEO_PATH_RE.search(parsed.path)
    if m:
        return m.group("id")
    # /hotels/detail/?hotelId=…, /hotels/v2/detail/…, link chia sẻ /hotels/w/detail/?hotelid=…
    if "/hotels" not in parsed.path.lower() or "detail" not in parsed.path.lower():
        return None
    for key, value in parse_qsl(parsed.query):
        if key.lower() == "hotelid" and value.isdigit() and int(value) > 0:
            return value
    return None


def canonical_url(hotel_id: str) -> str:
    return f"https://vn.trip.com/hotels/detail/?hotelId={hotel_id}"


def hotel_id(listing: ListingRef) -> str:
    return listing.external_id or listing.listing_key


def build_detail_url(
    listing: ListingRef, checkin: date, nights: int, adults: int, currency: str
) -> str:
    checkout = checkin + timedelta(days=nights)
    return (
        f"{canonical_url(hotel_id(listing))}&checkIn={checkin.isoformat()}"
        f"&checkOut={checkout.isoformat()}&adult={adults}&crn=1&children=0&curr={currency}"
    )
