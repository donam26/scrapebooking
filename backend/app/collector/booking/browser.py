import time
from datetime import date

from playwright.async_api import async_playwright

from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.playwright_bootstrap import (
    ChallengeNotSolved,
    browser_user_agent,
    wait_until_ready,
)
from app.collector.booking.results import failed_result, probe_result_from_page
from app.collector.booking.selectors import dates_dropped, shown_other_checkin
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.proxy import ProxyProvider
from app.domain.models import CalendarResult, HotelRef, ProbeMethod, ProbeResult, ProbeStatus
from app.logging import get_logger

log = get_logger(__name__)


class BrowserCollector:
    """Provider dự phòng: render toàn phần bằng Chromium cho một probe. Mỗi probe một IP mới."""

    def __init__(
        self, proxy_provider: ProxyProvider, headless: bool = True, timeout_ms: int = 45_000
    ) -> None:
        self._proxies = proxy_provider
        self._headless = headless
        self._timeout_ms = timeout_ms

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return CalendarResult(ok=False, error="browser collector does not fetch calendars")

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        currency = currency_for(hotel.country_code)
        url = build_hotel_url(hotel, checkin, nights, adults, currency)
        proxy = self._proxies.new_endpoint(hotel.country_code)
        t0 = time.monotonic()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self._headless,
                proxy={
                    "server": proxy.server,
                    "username": proxy.username or "",
                    "password": proxy.password or "",
                },
            )
            try:
                context = await browser.new_context(
                    locale="en-GB", user_agent=await browser_user_agent(browser)
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    await wait_until_ready(page, self._timeout_ms)
                except ChallengeNotSolved as exc:
                    log.warning("browser_probe_blocked", hotel=hotel.id, checkin=str(checkin))
                    return failed_result(
                        ProbeStatus.BLOCKED,
                        method=ProbeMethod.BROWSER,
                        checkin=checkin,
                        nights=nights,
                        adults=adults,
                        error=str(exc),
                        session_id=f"browser:{proxy.id}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                html = await page.content()
                other = shown_other_checkin(html, checkin)
                if other is not None:
                    return failed_result(
                        ProbeStatus.ERROR,
                        method=ProbeMethod.BROWSER,
                        checkin=checkin,
                        nights=nights,
                        adults=adults,
                        error=f"booking showed other dates: checkin {other}",
                        session_id=f"browser:{proxy.id}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                if dates_dropped(html):
                    log.warning("browser_probe_dates_dropped", hotel=hotel.id, checkin=str(checkin))
                    return failed_result(
                        ProbeStatus.BLOCKED,
                        method=ProbeMethod.BROWSER,
                        checkin=checkin,
                        nights=nights,
                        adults=adults,
                        error="dates dropped (soft block)",
                        session_id=f"browser:{proxy.id}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
            except Exception as exc:  # noqa: BLE001
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.BROWSER,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error=f"{type(exc).__name__}: {exc}",
                    session_id=f"browser:{proxy.id}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            finally:
                await browser.close()
        parsed = parse_hotel_page(html, currency, adults)
        return probe_result_from_page(
            parsed,
            method=ProbeMethod.BROWSER,
            checkin=checkin,
            nights=nights,
            adults=adults,
            raw_html=html,
            http_status=200,
            session_id=f"browser:{proxy.id}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
