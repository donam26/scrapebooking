import re
from dataclasses import dataclass
from urllib.parse import urlparse

_PATH_RE = re.compile(
    r"^/hotel/(?P<cc>[a-z]{2})/(?P<name>[a-z0-9\-]+?)(?:\.[a-z]{2}(?:-[a-z]{2})?)?\.html$"
)


class BookingUrlError(ValueError):
    pass


@dataclass(frozen=True)
class BookingHotelUrl:
    country_code: str
    slug: str
    canonical_url: str

    @property
    def pagename(self) -> str:
        return self.slug.split("/", 1)[1]


def parse_booking_url(url: str) -> BookingHotelUrl:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc.endswith("booking.com"):
        raise BookingUrlError(f"not a booking.com url: {url}")
    m = _PATH_RE.match(parsed.path)
    if not m:
        raise BookingUrlError(f"not a hotel page url: {url}")
    cc, name = m.group("cc"), m.group("name")
    slug = f"{cc}/{name}"
    return BookingHotelUrl(
        country_code=cc,
        slug=slug,
        canonical_url=f"https://www.booking.com/hotel/{slug}.html",
    )
