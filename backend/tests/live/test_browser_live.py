from datetime import date, timedelta

import pytest

from app.collector.booking.browser import BrowserCollector
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings
from app.domain.models import HotelRef, ProbeStatus


@pytest.mark.live
async def test_browser_probe_real() -> None:
    s = get_settings()
    hotel = HotelRef(
        0, "vn", "vn/the-reverie-saigon", "https://www.booking.com/hotel/vn/the-reverie-saigon.html"
    )
    collector = BrowserCollector(
        StaticProxyProvider(s.proxy_url_template), headless=s.playwright_headless
    )
    r = await collector.probe(hotel, date.today() + timedelta(days=14), nights=1, adults=2)
    assert r.status in (ProbeStatus.OK, ProbeStatus.SOLD_OUT)
    if r.status == ProbeStatus.OK:
        assert r.offers and r.offers[0].rates
