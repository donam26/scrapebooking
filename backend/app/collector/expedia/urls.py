"""URL Expedia (thuần): nhận diện trang khách sạn trên mọi tên miền quốc gia. Chưa có collector
(Akamai + giới hạn GraphQL, xem
plans/261001-1441-multi-channel-ota-standards/reports/spike-traveloka-mytour-expedia.md)."""

import re
from urllib.parse import urlparse

from app.channels.registry import ListingUrl, UnsupportedUrl

# expedia.com, expedia.com.vn, expedia.co.uk…
_HOST_RE = re.compile(r"(?:^|\.)expedia\.(?:com|co|[a-z]{2})(?:\.[a-z]{2})?$")
# .../Ho-Chi-Minh-City-Hotels-Rex-Hotel-Saigon.h481670.Hotel-Information
# .../Ho-Chi-Minh-City-Khach-San-Rex-Hotel.h481670.Thong-tin-khach-san (bản tiếng Việt)
_PATH_RE = re.compile(r"^/(?:[^/]+/)*(?P<name>[A-Za-z0-9-]*)\.h(?P<id>\d+)\.[A-Za-z-]+$")


def parse_url(url: str) -> ListingUrl | None:
    parsed = urlparse(url.strip())
    if not _HOST_RE.search((parsed.hostname or "").lower()):
        return None
    m = _PATH_RE.match(parsed.path)
    if not m:
        raise UnsupportedUrl(
            "not_hotel_page",
            channel="Expedia",
            example="expedia.com.vn/Ten-Khach-San.h123456.Hotel-Information",
        )
    hotel_id, name = m.group("id"), m.group("name") or "Hotel"
    return ListingUrl(
        channel="expedia",
        listing_key=hotel_id,
        # Điểm bán VN; expedia.com.vn tự chuyển ".Hotel-Information" sang đường dẫn tiếng Việt.
        url=f"https://www.expedia.com.vn/{name}.h{hotel_id}.Hotel-Information",
        external_id=hotel_id,
    )
