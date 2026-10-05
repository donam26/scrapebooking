"""Tìm địa điểm (thành phố/quận/vùng) trên Booking qua autocomplete.json → dest_id/dest_type.

API gợi ý là JSON nhẹ, không qua challenge: gọi bằng curl_cffi qua proxy giống
`BookingCollector.suggest`, có tính vào ngân sách request của kênh.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.collector.base import ListingBlocked
from app.collector.factory import NoBudget, RequestBudget
from app.collector.proxy import ProxyProvider

# Cùng endpoint với BookingCollector.suggest (không import collector: kéo theo Playwright vào API).
AUTOCOMPLETE_URL = "https://accommodations.booking.com/autocomplete.json"
# Loại địa điểm quét được cả chợ (bỏ khách sạn lẻ, sân bay, địa danh).
AREA_DEST_TYPES = ("city", "district", "region")


@dataclass(frozen=True)
class Destination:
    dest_id: str
    dest_type: str
    name: str  # "Ho Chi Minh City"
    label: str  # "Ho Chi Minh City, Ho Chi Minh Municipality, Vietnam"
    country_code: str | None
    nr_hotels: int | None  # số chỗ ở kênh báo cho địa điểm (gồm nhà/căn hộ)
    lat: float | None
    lng: float | None


def parse_destinations(payload: dict[str, Any]) -> list[Destination]:
    out: list[Destination] = []
    for r in payload.get("results") or []:
        if not isinstance(r, dict) or r.get("dest_type") not in AREA_DEST_TYPES:
            continue
        if not r.get("dest_id"):
            continue
        lat, lng = r.get("latitude"), r.get("longitude")
        out.append(
            Destination(
                dest_id=str(r["dest_id"]),
                dest_type=str(r["dest_type"]),
                name=str(r.get("label1") or r.get("label") or r["dest_id"]),
                label=str(r.get("label") or r.get("label1") or ""),
                country_code=(str(r["cc1"]).lower() if r.get("cc1") else None),
                nr_hotels=int(r["nr_hotels"]) if r.get("nr_hotels") is not None else None,
                lat=float(lat) if lat is not None else None,
                lng=float(lng) if lng is not None else None,
            )
        )
    return out


class DestinationSearch(Protocol):
    async def __call__(self, query: str, country: str) -> list[Destination]: ...


class BookingDestinationSearch:
    def __init__(
        self, proxy_provider: ProxyProvider, budget: RequestBudget | None = None, size: int = 10
    ) -> None:
        self._proxies = proxy_provider
        self._budget = budget or NoBudget()
        self._size = size

    async def __call__(self, query: str, country: str) -> list[Destination]:
        from curl_cffi.requests import AsyncSession

        proxy = self._proxies.new_endpoint(country)
        await self._budget.acquire()
        async with AsyncSession(
            impersonate="chrome", proxies={"http": proxy.url, "https": proxy.url}, timeout=30
        ) as client:
            r = await client.post(
                AUTOCOMPLETE_URL,
                json={"query": query, "language": "en-gb", "size": self._size},
                headers={
                    "Origin": "https://www.booking.com",
                    "Referer": "https://www.booking.com/",
                },
            )
        if r.status_code != 200:
            raise ListingBlocked(f"autocomplete http {r.status_code}")
        try:
            return parse_destinations(json.loads(r.text))
        except json.JSONDecodeError as exc:
            raise ListingBlocked(f"autocomplete invalid json: {exc.msg}") from exc
