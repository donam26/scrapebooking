"""Lưu HTML thật của trang khách sạn Booking làm fixture.

Dùng: uv run python scripts/capture_fixture.py <booking_hotel_url> <checkin YYYY-MM-DD> <nights> <tên_fixture>
Ví dụ: uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-10-10 1 available_no_badge
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings
from app.domain.booking_url import parse_booking_url
from app.domain.models import HotelRef

OUT = Path(__file__).parent.parent / "tests" / "fixtures" / "html"


async def main(url: str, checkin: str, nights: str, name: str) -> None:
    s = get_settings()
    ref = parse_booking_url(url)
    hotel = HotelRef(
        id=0, country_code=ref.country_code, slug=ref.slug, canonical_url=ref.canonical_url
    )
    target = build_hotel_url(
        hotel,
        date.fromisoformat(checkin),
        int(nights),
        s.default_adults,
        currency_for(ref.country_code),
    )
    proxy = StaticProxyProvider(s.proxy_url_template).new_endpoint(ref.country_code)
    result = await PlaywrightBootstrapper(headless=s.playwright_headless).bootstrap(proxy, target)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.html"
    path.write_text(result.html, encoding="utf-8")
    print(f"saved {path} ({len(result.html)} bytes) from {target}")


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:5]))
