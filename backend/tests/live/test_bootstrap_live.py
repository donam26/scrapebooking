import pytest

from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings


@pytest.mark.live
async def test_bootstrap_real_booking() -> None:
    s = get_settings()
    proxy = StaticProxyProvider(s.proxy_url_template).new_endpoint("vn")
    result = await PlaywrightBootstrapper(headless=s.playwright_headless).bootstrap(
        proxy, "https://www.booking.com/hotel/vn/the-reverie-saigon.html"
    )
    assert "Chrome" in result.user_agent
    assert len(result.cookies) > 0
    assert "hprt-table" in result.html or "hp_hotel_name" in result.html
