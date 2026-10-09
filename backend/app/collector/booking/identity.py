"""Định danh khách sạn trên Booking (thuần): tên, b_hotel_id, địa chỉ, toạ độ, hạng sao; và kết quả
API gợi ý (autocomplete) → ứng viên listing."""

import json
import re
from decimal import Decimal
from typing import Any

from selectolax.parser import HTMLParser

from app.collector.booking import selectors as S
from app.collector.booking.urls import canonical_url
from app.domain.models import ListingIdentity

_LD_JSON_RE = re.compile(
    r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL
)
_LATLNG_RE = re.compile(r'data-atlas-latlng="(-?\d+\.\d+),(-?\d+\.\d+)"')
_HOTEL_CLASS_RE = re.compile(r"hotel_class:\s*(\d)")


def _hotel_ld(html: str) -> dict[str, Any]:
    for m in _LD_JSON_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") in ("Hotel", "Resort", "LodgingBusiness"):
            return data
    return {}


def parse_identity(html: str, slug: str) -> ListingIdentity:
    tree = HTMLParser(html)
    ld = _hotel_ld(html)
    raw_address = ld.get("address")
    address: dict[str, Any] = raw_address if isinstance(raw_address, dict) else {}
    name = None
    for selector in S.HOTEL_NAME_PRIORITY:
        node = tree.css_first(selector)
        if node is not None and node.text(strip=True):
            name = " ".join(node.text(separator=" ").split())
            break
    hotel_id = S.HOTEL_ID_RE.search(html)
    latlng = _LATLNG_RE.search(html)
    stars = _HOTEL_CLASS_RE.search(html)
    return ListingIdentity(
        external_id=hotel_id.group(1) if hotel_id else None,
        name=name or ld.get("name"),
        url=canonical_url(slug),
        address=address.get("streetAddress"),
        city=address.get("addressRegion"),
        country_code=slug.split("/", 1)[0],
        lat=float(latlng.group(1)) if latlng else None,
        lng=float(latlng.group(2)) if latlng else None,
        star_rating=Decimal(stars.group(1)) if stars and stars.group(1) != "0" else None,
    )
