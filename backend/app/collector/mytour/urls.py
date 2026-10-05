"""URL Mytour (thuần): nhận diện trang khách sạn mytour.vn/khach-san/<id>-<slug>.html."""

import re
from urllib.parse import urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl, host_matches

# /khach-san/23812-sol-by-melia-phu-quoc.html; trang tỉnh/quận là /khach-san/tp2/..., /td446/...
_PATH_RE = re.compile(r"^/khach-san/(?P<id>\d+)-(?P<slug>[a-z0-9-]+)\.html$")
# slug trong API có đuôi "-h<id>": "sol-by-melia-phu-quoc-h23812"
_API_SLUG_SUFFIX = re.compile(r"-h\d+$")


def parse_url(url: str) -> ListingUrl | None:
    if not host_matches(url, "mytour.vn"):
        return None
    m = _PATH_RE.match(urlparse(url.strip()).path)
    if not m:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="Mytour",
            example="mytour.vn/khach-san/12345-ten-khach-san.html",
        )
    hotel_id = m.group("id")
    return ListingUrl(
        channel="mytour",
        listing_key=hotel_id,
        url=canonical_url(hotel_id, m.group("slug")),
        external_id=hotel_id,
    )


def canonical_url(hotel_id: int | str, slug: str) -> str:
    """`slug` nhận cả dạng trên URL lẫn dạng API (có đuôi -h<id>)."""
    return f"https://mytour.vn/khach-san/{hotel_id}-{_API_SLUG_SUFFIX.sub('', slug)}.html"
