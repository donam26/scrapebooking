"""Chromium sống qua nhiều probe cho Trip.com.

API danh sách phòng (`getHotelRoomListOversea`) đòi header `phantom-token` do JS chống bot của trang
sinh riêng cho từng request (dùng lại token hoặc gọi thiếu → `htlSpiderActionErrorCode: 4030`, trang
chuyển sang đăng nhập). Vì vậy để chính trang gọi API: mỗi probe mở trang chi tiết với ngày cần quét
và bắt response. Một trình duyệt dùng cho cả session (cookie + HTTP cache của JS); không dùng
`page.route` vì route tắt HTTP cache của Chromium.

Headless bị nhận ra nếu UA/client hints còn "HeadlessChrome" hoặc lệch phiên bản: dùng Chromium đầy
đủ (`channel="chromium"`, headless mới), tắt cờ AutomationControlled, đặt UA + userAgentMetadata
khớp nhau qua CDP.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from app.collector.booking.playwright_bootstrap import browser_user_agent
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult
from app.logging import get_logger

log = get_logger(__name__)

ROOM_LIST_PATH = "/restapi/soa2/33269/getHotelRoomListOversea"
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--blink-settings=imagesEnabled=false",  # bớt tải qua proxy mà vẫn giữ HTTP cache
]
_HIDE_WEBDRIVER = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


def ua_override(user_agent: str, accept_language: str = "vi-VN,vi;q=0.9") -> dict[str, Any]:
    """Tham số CDP `Network.setUserAgentOverride`: UA và client hints (sec-ch-ua) cùng phiên bản."""
    m = re.search(r"Chrome/(\d+)", user_agent)
    major = m.group(1) if m else "0"
    if "Windows" in user_agent:
        platform, nav_platform = "Windows", "Win32"
    elif "Mac OS X" in user_agent:
        platform, nav_platform = "macOS", "MacIntel"
    else:
        platform, nav_platform = "Linux", "Linux x86_64"
    return {
        "userAgent": user_agent,
        "acceptLanguage": accept_language,
        "platform": nav_platform,
        "userAgentMetadata": {
            "brands": [
                {"brand": "Chromium", "version": major},
                {"brand": "Google Chrome", "version": major},
                {"brand": "Not_A Brand", "version": "99"},
            ],
            "fullVersion": f"{major}.0.0.0",
            "platform": platform,
            "platformVersion": "",
            "architecture": "x86",
            "model": "",
            "mobile": False,
        },
    }


def left_detail(url: str) -> str | None:
    """Trang đã rời trang chi tiết: "signin" (bị nghi bot) | "other" (VD id sai → trang chủ)."""
    path = urlparse(url).path.lower()
    if "/account/signin" in path or "/login" in path:
        return "signin"
    if "/hotels" not in path or "detail" not in path:
        return "other"
    return None


@dataclass(frozen=True)
class DetailLoad:
    final_url: str
    room_list: str | None  # body JSON của API danh sách phòng, None nếu không bắt được
    html: str | None  # DOM lúc có danh sách phòng (SSR có tên, "lần đặt gần nhất")
    http_status: int | None
    left: str | None  # left_detail() của URL cuối


class LiveBrowser:
    def __init__(
        self, pw: Playwright, browser: Browser, context: BrowserContext, page: Page, ua: str
    ) -> None:
        self._pw = pw
        self._browser = browser
        self._context = context
        self._page = page
        self.user_agent = ua
        self._lock = asyncio.Lock()

    @classmethod
    async def launch(cls, proxy: ProxyEndpoint, headless: bool) -> "LiveBrowser":
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(
                headless=headless,
                channel="chromium",
                args=_LAUNCH_ARGS,
                proxy={
                    "server": proxy.server,
                    "username": proxy.username or "",
                    "password": proxy.password or "",
                },
            )
            ua = await browser_user_agent(browser)
            context = await browser.new_context(
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1366, "height": 850},
                user_agent=ua,
            )
            await context.add_init_script(_HIDE_WEBDRIVER)
            page = await context.new_page()
            cdp = await context.new_cdp_session(page)
            await cdp.send("Network.setUserAgentOverride", ua_override(ua))
        except Exception:
            await pw.stop()
            raise
        log.info("tripcom_browser_started", proxy=proxy.id)
        return cls(pw, browser, context, page, ua)

    async def load_detail(self, url: str, timeout_s: float) -> DetailLoad:
        """Mở trang chi tiết, chờ response API danh sách phòng của chính trang đó."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            got: asyncio.Future[tuple[int, str]] = loop.create_future()
            pending: set[asyncio.Task[None]] = set()

            async def capture(response: Response) -> None:
                if ROOM_LIST_PATH not in response.url or got.done():
                    return
                try:
                    body = await response.text()
                except Error:
                    return
                if not got.done():
                    got.set_result((response.status, body))

            def on_response(response: Response) -> None:
                task = asyncio.ensure_future(capture(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            deadline = loop.time() + timeout_s
            self._page.on("response", on_response)
            try:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
                while not got.done() and loop.time() < deadline:
                    if left_detail(self._page.url):
                        break
                    await asyncio.sleep(0.25)
            finally:
                self._page.remove_listener("response", on_response)
            final_url = self._page.url
            if not got.done():
                return DetailLoad(final_url, None, None, None, left_detail(final_url))
            status, body = got.result()
            html: str | None = None
            try:
                html = await self._page.content()
            except Error:
                pass  # trang đang chuyển đi (VD sang đăng nhập)
            return DetailLoad(final_url, body, html, status, left_detail(final_url))

    async def close(self) -> None:
        try:
            await self._browser.close()
        except Error:
            pass
        await self._pw.stop()


class TripcomBootstrapper:
    """SessionBootstrapper: mỗi session (một IP proxy) là một LiveBrowser, tra theo `proxy.id`."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self.live: dict[str, LiveBrowser] = {}

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        browser = await LiveBrowser.launch(proxy, self._headless)
        self.live[proxy.id] = browser
        return BootstrapResult(cookies={}, user_agent=browser.user_agent, csrf_token=None, html="")

    async def close(self, proxy_id: str) -> None:
        browser = self.live.pop(proxy_id, None)
        if browser is not None:
            await browser.close()

    async def close_others(self, keep: str) -> None:
        """Đóng trình duyệt của các session SessionManager đã cho hết hạn."""
        for proxy_id in [p for p in self.live if p != keep]:
            await self.close(proxy_id)

    async def close_all(self) -> None:
        for proxy_id in list(self.live):
            await self.close(proxy_id)
