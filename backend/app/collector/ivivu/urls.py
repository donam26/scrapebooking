"""URL ivivu.com (thuần): nhận diện trang khách sạn."""

import re
from urllib.parse import urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches

# Trang khách sạn: /khach-san-<vùng>/<slug>. Trang vùng chỉ có một đoạn (/khach-san-phu-quoc).
_PATH_RE = re.compile(r"^/(?P<region>khach-san-[a-z0-9\-]+)/(?P<hotel>[a-z0-9\-]+)/?$")


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "ivivu.com"):
        return None
    m = _PATH_RE.match(urlparse(url.strip()).path.lower())
    if not m:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="iVIVU",
            example="ivivu.com/khach-san-phu-quoc/ten-khach-san",
        )
    key = f"{m.group('region')}/{m.group('hotel')}"
    return ListingUrl(channel="ivivu", listing_key=key, url=canonical_url(key), country_code="vn")


def canonical_url(listing_key: str) -> str:
    return f"https://www.ivivu.com/{listing_key.strip('/')}"
