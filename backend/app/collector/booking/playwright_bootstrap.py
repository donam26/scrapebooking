import asyncio

from playwright.async_api import Browser, Page, async_playwright

from app.collector.booking.selectors import READY_SELECTOR, extract_csrf_token
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult
from app.logging import get_logger

log = get_logger(__name__)


class ChallengeNotSolved(RuntimeError):
    pass


def normalize_user_agent(user_agent: str) -> str:
    """Chromium headless tự khai "HeadlessChrome": Booking nhận ra và 301 về trang không có ngày
    (bỏ checkin/checkout), nên dùng UA như Chrome thường cho cả trình duyệt lẫn curl."""
    return user_agent.replace("HeadlessChrome", "Chrome")


async def browser_user_agent(browser: Browser) -> str:
    """UA thật của bản Chromium đang chạy (đúng phiên bản, đúng nền tảng), đã bỏ dấu headless."""
    context = await browser.new_context()
    try:
        page = await context.new_page()
        user_agent: str = await page.evaluate("() => navigator.userAgent")
    finally:
        await context.close()
    return normalize_user_agent(user_agent)


async def wait_until_ready(page: Page, timeout_ms: int, poll_ms: int = 1000) -> None:
    waited = 0
    while waited <= timeout_ms:
        if await page.locator(READY_SELECTOR).count() > 0:
            return
        await asyncio.sleep(poll_ms / 1000)
        waited += poll_ms
    raise ChallengeNotSolved(f"page not ready after {timeout_ms}ms: {page.url}")


class PlaywrightBootstrapper:
    """Mở Chromium thật qua proxy, vượt challenge AWS WAF, trả cookie + UA + csrf."""

    def __init__(self, headless: bool = True, challenge_timeout_ms: int = 45_000) -> None:
        self._headless = headless
        self._timeout_ms = challenge_timeout_ms

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
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
                    locale="en-GB",
                    viewport={"width": 1366, "height": 850},
                    user_agent=await browser_user_agent(browser),
                )
                page = await context.new_page()
                await page.goto(warmup_url, wait_until="domcontentloaded", timeout=60_000)
                await wait_until_ready(page, self._timeout_ms)
                html = await page.content()
                cookies = {c["name"]: c["value"] for c in await context.cookies()}
                user_agent: str = await page.evaluate("() => navigator.userAgent")
                log.info("session_bootstrapped", proxy=proxy.id, cookies=len(cookies))
                return BootstrapResult(
                    cookies=cookies,
                    user_agent=user_agent,
                    csrf_token=extract_csrf_token(html),
                    html=html,
                )
            finally:
                await browser.close()
