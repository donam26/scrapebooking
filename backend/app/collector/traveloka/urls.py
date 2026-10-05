"""URL Traveloka (thuần): nhận diện trang khách sạn. Chưa có collector (DataDome chặn, xem
plans/261001-1441-multi-channel-ota-standards/reports/spike-traveloka-mytour-expedia.md)."""

import re
from urllib.parse import urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches

# /vi-vn/hotel/vietnam/an-lam-retreats-saigon-river-1000000393505 (tiền tố ngôn ngữ tuỳ chọn).
# Trang vùng/thành phố có thêm một cấp: /hotel/vietnam/region/phu-quoc-island-10010231.
_PATH_RE = re.compile(
    r"^(?:/[a-z]{2}-[a-z]{2})?/hotel/(?P<country>[a-z-]+)/(?P<slug>[a-z0-9-]+)-(?P<id>\d{6,})/?$"
)
_COUNTRY_CODES = {"vietnam": "vn"}


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "traveloka.com"):
        return None
    m = _PATH_RE.match(urlparse(url.strip()).path)
    if not m:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="Traveloka",
            example="traveloka.com/vi-vn/hotel/vietnam/ten-khach-san-1000000123456",
        )
    country, hotel_id = m.group("country"), m.group("id")
    return ListingUrl(
        channel="traveloka",
        listing_key=hotel_id,
        url=f"https://www.traveloka.com/vi-vn/hotel/{country}/{m.group('slug')}-{hotel_id}",
        country_code=_COUNTRY_CODES.get(country),
        external_id=hotel_id,
    )
