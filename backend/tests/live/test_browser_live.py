from datetime import date, timedelta

import pytest

from app.collector.booking.browser import BrowserCollector
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings
from app.domain.models import ProbeStatus
from tests.fakes import booking_listing


@pytest.mark.live
async def test_browser_probe_real() -> None:
    s = get_settings()
    hotel = booking_listing(0, "vn/the-reverie-saigon")
    collector = BrowserCollector(
        StaticProxyProvider(s.proxy_templates),
        headless=s.playwright_headless,
        currency=s.scan_currency,
    )
    r = await collector.probe(hotel, date.today() + timedelta(days=14), nights=1, adults=2)
    assert r.status in (ProbeStatus.OK, ProbeStatus.SOLD_OUT)
    if r.status == ProbeStatus.OK:
        assert r.offers and r.offers[0].rates
