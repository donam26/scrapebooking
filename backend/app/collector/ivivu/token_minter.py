"""Lấy token `X-ivv-key` cho API giá của ivivu bằng Chromium thật.

ivivu tự viết widget chống bot (`res.ivivu.com/js/ivv-btw-ob.js`, giống Turnstile): mỗi lần gọi
widget xin challenge (`gatewaycrm/get-session/challenge`), chạy đoạn JS challenge, gửi dấu vân tay
trình duyệt (UA, navigator.webdriver + kết quả BotD, kích thước màn hình, location.href) tới
`gatewaycrm/get-session/<site key>` và nhận token. Token **dùng một lần**, không gắn IP hay TLS.

Vì vậy giữ một trang ivivu mở suốt session và gọi widget của chính trang để lấy token mới cho mỗi
probe (2 request nhỏ); request giá nặng (~3 MB) đi bằng curl_cffi. Trình duyệt chạy chế độ headless
mới (`channel="chromium"`), bỏ cờ AutomationControlled và chữ "HeadlessChrome" trong UA: thiếu một
trong hai thì token trả về bị API giá từ chối (403 Invalid_token_ivv).
"""

import asyncio
import itertools
from urllib.parse import urlsplit

from playwright.async_api import Browser, Page, Playwright, Request, Route, async_playwright

from app.collector.booking.playwright_bootstrap import browser_user_agent
from app.collector.ivivu.api import API_BASE
from app.collector.proxy import ProxyEndpoint
from app.logging import get_logger

log = get_logger(__name__)

SITE_KEY = "NgwAEb2WMZ4e9DF7zGu3ChqLH6"  # botDetectionSiteKey trong cấu hình web ivivu
FLAG_URL = f"{API_BASE}/web_prot/config/FlagSetting?clientType=hotel"
FLAG_OFF = 0  # 1 = Cloudflare Turnstile (không hỗ trợ), 2 = widget riêng của ivivu (hiện tại)
_BLOCKED_TYPES = {"image", "media", "font"}
# Trang chỉ cần tải app Angular + cờ + widget token. Chặn mọi API khác của ivivu (giá ~3 MB, combo,
# đánh giá…) và bên thứ ba (analytics): ít request tới ivivu hơn, mở trang nhanh hơn.
_ALLOWED_HOSTS = ("www.ivivu.com", "res.ivivu.com")
_ALLOWED_API = ("/web_prot/config/FlagSetting", "/gatewaycrm/get-session/")

_WIDGET_READY_JS = "() => !!(window._myBotWidgetGlobal && window._myBotWidgetGlobal.initWidgets)"
_FLAG_JS = """
async (u) => { try { return (await (await fetch(u)).json()).flagOn; } catch (e) { return null; } }
"""

# Widget riêng của collector (không đụng widget của trang). Lần đầu tạo phần tử .ivv-s-widget rồi
# initWidgets(); các lần sau refreshWidget(id). Widget gọi window[data-callback + id](token|null).
_MINT_JS = """
async ({id, siteKey, timeoutMs}) => {
  const g = window._myBotWidgetGlobal;
  const cb = '__sbTok';
  return await new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs);
    window[cb + id] = (token) => { clearTimeout(timer); resolve(token || null); };
    if ((g.storedWidgets || []).some((w) => w.widgetId === id)) { g.refreshWidget(id); return; }
    const known = (g.storedWidgets || []).find((w) => w.siteKey);
    const el = document.createElement('div');
    el.className = 'ivv-s-widget';
    el.setAttribute('data-widgetid', id);
    el.setAttribute('data-sitekey', known ? known.siteKey : siteKey);
    el.setAttribute('data-callback', cb);
    document.body.appendChild(el);
    g.initWidgets();
  });
}
"""


class TokenUnavailable(RuntimeError):
    """Không dựng được trang lấy token (widget không tải, ivivu chuyển sang Turnstile…)."""


_ids = itertools.count(1)


class BrowserTokenMinter:
    """Một Chromium + một trang ivivu cho một session. Gọi `launch()` để mở, `close()` để đóng."""

    def __init__(
        self,
        pw: Playwright,
        browser: Browser,
        page: Page,
        user_agent: str,
        cookies: dict[str, str],
        needs_token: bool,
        mint_timeout_ms: int,
    ) -> None:
        self._pw = pw
        self._browser = browser
        self._page = page
        self.user_agent = user_agent
        self.cookies = cookies
        self._needs_token = needs_token
        self._timeout_ms = mint_timeout_ms
        self._widget_id = f"sb{next(_ids)}"
        self._lock = asyncio.Lock()

    @classmethod
    async def launch(
        cls,
        proxy: ProxyEndpoint,
        warmup_url: str,
        headless: bool = True,
        ready_timeout_ms: int = 30_000,
        mint_timeout_ms: int = 20_000,
    ) -> "BrowserTokenMinter":
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(
                channel="chromium",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                proxy={
                    "server": proxy.server,
                    "username": proxy.username or "",
                    "password": proxy.password or "",
                },
            )
        except Exception:
            await pw.stop()
            raise
        try:
            context = await browser.new_context(
                locale="vi-VN",
                viewport={"width": 1366, "height": 850},
                user_agent=await browser_user_agent(browser),
            )
            await context.route("**/*", _route)
            page = await context.new_page()
            await page.goto(warmup_url, wait_until="domcontentloaded", timeout=60_000)
            needs_token = await _wait_widget(page, ready_timeout_ms)
            cookies = {c["name"]: c["value"] for c in await context.cookies()}
            user_agent: str = await page.evaluate("() => navigator.userAgent")
        except Exception:
            await browser.close()
            await pw.stop()
            raise
        log.info("ivivu_minter_ready", proxy=proxy.id, needs_token=needs_token)
        return cls(pw, browser, page, user_agent, cookies, needs_token, mint_timeout_ms)

    async def mint(self) -> str | None:
        """Token mới (dùng một lần); "" nếu ivivu đang tắt kiểm tra bot; None nếu thất bại."""
        if not self._needs_token:
            return ""
        async with self._lock:
            try:
                token = await self._page.evaluate(
                    _MINT_JS,
                    {"id": self._widget_id, "siteKey": SITE_KEY, "timeoutMs": self._timeout_ms},
                )
            except Exception as exc:  # noqa: BLE001 - trang đóng/crash: session hỏng
                log.warning("ivivu_mint_failed", error=f"{type(exc).__name__}: {exc}")
                return None
        return token if isinstance(token, str) and token else None

    async def close(self) -> None:
        try:
            await self._browser.close()
        finally:
            await self._pw.stop()


async def _route(route: Route, request: Request) -> None:
    if _allowed(request.url, request.resource_type):
        await route.continue_()
    else:
        await route.abort()


def _allowed(url: str, resource_type: str) -> bool:
    if resource_type in _BLOCKED_TYPES:
        return False
    parts = urlsplit(url)
    if parts.hostname in _ALLOWED_HOSTS:
        return not parts.path.startswith("/cdn-cgi/")  # Cloudflare RUM
    return url.startswith(API_BASE) and parts.path.startswith(_ALLOWED_API)


async def _wait_widget(page: Page, timeout_ms: int) -> bool:
    """True: widget sẵn sàng (cần token). False: ivivu tắt kiểm tra bot (không cần token)."""
    try:
        await page.wait_for_function(_WIDGET_READY_JS, timeout=timeout_ms)
        return True
    except Exception as exc:
        flag = await page.evaluate(_FLAG_JS, FLAG_URL)
        if flag == FLAG_OFF:
            return False
        raise TokenUnavailable(f"bot widget not loaded (flagOn={flag})") from exc
