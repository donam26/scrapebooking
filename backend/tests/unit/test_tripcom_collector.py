import json
from collections import deque
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.clock import FixedClock
from app.collector.base import ListingBlocked
from app.collector.factory import CollectorDeps
from app.collector.proxy import ProxyEndpoint, StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import BootstrapResult
from app.collector.tripcom.browser import DetailLoad, TripcomBootstrapper, left_detail, ua_override
from app.collector.tripcom.collector import TripcomCollector
from app.domain.models import DemandKind, ListingRef, ProbeMethod, ProbeStatus
from tests.conftest import FIXTURES_DIR
from tests.fakes import no_sleep

FIX = FIXTURES_DIR / "tripcom"
LISTING = ListingRef(
    1, "tripcom", "6648653", "https://vn.trip.com/hotels/detail/?hotelId=6648653", "vn", "6648653"
)
DETAIL_URL = "https://vn.trip.com/hotels/detail/?hotelId=6648653&checkIn=2026-10-15"
OK_LOAD = DetailLoad(
    final_url=DETAIL_URL,
    room_list=(FIX / "roomlist_muongthanh.json").read_text(),
    html=(FIX / "detail_melia.html").read_text(),
    http_status=200,
    left=None,
)
BLOCKED_LOAD = DetailLoad(
    final_url=DETAIL_URL,
    room_list=(FIX / "roomlist_spider_blocked.json").read_text(),
    html=None,
    http_status=200,
    left=None,
)


class ScriptedBrowser:
    def __init__(self, loads: deque[DetailLoad]) -> None:
        self._loads = loads
        self.urls: list[str] = []
        self.closed = False

    async def load_detail(self, url: str, timeout_s: float) -> DetailLoad:
        self.urls.append(url)
        return self._loads.popleft()

    async def close(self) -> None:
        self.closed = True


class ScriptedBootstrapper(TripcomBootstrapper):
    """Không mở Chromium: mỗi session nhận một ScriptedBrowser dùng chung hàng đợi kết quả."""

    def __init__(self, *loads: DetailLoad) -> None:
        super().__init__(headless=True)
        self.loads = deque(loads)
        self.browsers: list[ScriptedBrowser] = []

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        browser = ScriptedBrowser(self.loads)
        self.browsers.append(browser)
        self.live[proxy.id] = browser  # type: ignore[assignment]
        return BootstrapResult(cookies={}, user_agent="ua", csrf_token=None, html="")


def collector(*loads: DetailLoad) -> tuple[TripcomCollector, ScriptedBootstrapper]:
    deps = CollectorDeps(
        proxy_provider=StaticProxyProvider("http://u:p@proxy.local:8000"),
        clock=FixedClock(datetime(2026, 10, 1, tzinfo=UTC)),
        limiter=RateLimiter(0, 0, sleep=no_sleep),
        currency="VND",
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=400,
    )
    browsers = ScriptedBootstrapper(*loads)
    return TripcomCollector(deps, browsers=browsers), browsers


async def test_probe_ok_builds_result_from_page_and_api() -> None:
    c, browsers = collector(OK_LOAD)
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.OK
    assert result.method == ProbeMethod.BROWSER
    assert result.checkout == date(2026, 10, 16)
    assert result.hotel_name == "Meliá Vinpearl Phu Quoc"  # từ trang (fixture Melia)
    assert result.external_id == "7047736"
    assert [o.external_room_id for o in result.offers] == ["95378465", "57220404"]
    assert result.raw_html is not None
    raw = json.loads(result.raw_html)
    assert raw["page"]["lastBooking"] == "Lần đặt gần nhất cách đây 18 phút"
    assert raw["roomList"]["data"]["searchBoxInfo"]["checkIn"] == "20261015"
    (signal,) = result.demand_signals
    assert (signal.kind, signal.value) == (DemandKind.LAST_BOOKED_MINUTES, Decimal(18))
    assert browsers.browsers[0].urls == [
        "https://vn.trip.com/hotels/detail/?hotelId=6648653&checkIn=2026-10-15"
        "&checkOut=2026-10-16&adult=2&crn=1&children=0&curr=VND"
    ]


async def test_probe_reuses_browser_between_dates() -> None:
    c, browsers = collector(OK_LOAD, OK_LOAD)
    await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert len(browsers.browsers) == 1
    assert len(browsers.browsers[0].urls) == 2


async def test_blocked_retires_session_and_retries_once() -> None:
    c, browsers = collector(BLOCKED_LOAD, OK_LOAD)
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.OK
    assert len(browsers.browsers) == 2
    assert browsers.browsers[0].closed is True
    assert list(browsers.live.values()) == [browsers.browsers[1]]


async def test_blocked_twice_reports_blocked() -> None:
    signin = DetailLoad("https://vn.trip.com/account/signin?backurl=x", None, None, None, "signin")
    c, _ = collector(BLOCKED_LOAD, signin)
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    assert result.error == "blocked: signin"


async def test_redirect_away_from_detail_is_blocked_not_broken() -> None:
    # Trang 200 chuyển về trang chủ: Trip.com không nói rõ "không tồn tại", chặn mềm cũng chuyển
    # hướng y hệt → BLOCKED + thu hồi session (trước đây not_found → listing broken vĩnh viễn).
    home = DetailLoad("https://vn.trip.com/?locale=vi-vn", None, None, None, "other")
    c, browsers = collector(home, home)
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    assert result.error == "blocked: redirected to https://vn.trip.com/?locale=vi-vn"
    assert [b.closed for b in browsers.browsers] == [True, True]
    assert browsers.live == {}


async def test_bootstrap_failure_is_blocked_result_not_exception() -> None:
    class Exploding(ScriptedBootstrapper):
        async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
            raise RuntimeError("chromium launch failed")

    deps = CollectorDeps(
        proxy_provider=StaticProxyProvider("http://u:p@proxy.local:8000"),
        clock=FixedClock(datetime(2026, 10, 1, tzinfo=UTC)),
        limiter=RateLimiter(0, 0, sleep=no_sleep),
        currency="VND",
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=400,
    )
    c = TripcomCollector(deps, browsers=Exploding())
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.BLOCKED and result.session_id is None
    assert result.error == "bootstrap: RuntimeError: chromium launch failed"


async def test_verify_200_without_hotel_data_is_blocked() -> None:
    c, _ = collector()
    seen: list[str] = []

    async def fake_request(method: str, url: str, **kwargs: object) -> tuple[int, str, str]:
        seen.append(url)
        return 200, "<html><body>Please wait</body></html>", "https://vn.trip.com/?x=1"

    c._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(ListingBlocked, match="no hotel data"):
        await c.verify(LISTING)
    assert seen == ["https://vn.trip.com/hotels/detail/?hotelId=6648653"]


async def test_expired_session_closes_browser_and_clears_rate_limiter() -> None:
    c, browsers = collector(OK_LOAD, OK_LOAD)
    await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    first = await c._sessions.get("vn", "x")
    for _ in range(400):
        c._sessions.mark_request(first)
    await c.probe(LISTING, date(2026, 10, 15), 1, 2)  # hết số request → session mới
    assert browsers.browsers[0].closed is True and len(browsers.browsers) == 2
    assert first.id not in c._deps.limiter._last


async def test_room_list_timeout_is_error() -> None:
    c, _ = collector(DetailLoad(DETAIL_URL, None, None, None, None))
    result = await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error is not None and result.error.startswith("timeout")


async def test_calendar_unsupported_and_close() -> None:
    c, browsers = collector(OK_LOAD)
    calendar = await c.fetch_calendar(LISTING, date(2026, 10, 15), 30, 2)
    assert (calendar.ok, calendar.error) == (False, "unsupported")
    await c.probe(LISTING, date(2026, 10, 15), 1, 2)
    await c.close()
    assert browsers.browsers[0].closed is True and browsers.live == {}


def test_left_detail() -> None:
    assert left_detail(DETAIL_URL) is None
    assert left_detail("https://vn.trip.com/hotels/v2/detail/?hotelId=1") is None
    assert left_detail("https://vn.trip.com/account/signin?backurl=x") == "signin"
    assert left_detail("https://vn.trip.com/?locale=vi-vn") == "other"


def test_ua_override_matches_client_hints() -> None:
    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    )
    params = ua_override(ua)
    assert params["userAgent"] == ua
    assert params["platform"] == "Linux x86_64"
    meta = params["userAgentMetadata"]
    assert meta["platform"] == "Linux"
    assert {b["version"] for b in meta["brands"][:2]} == {"153"}
    assert all("Headless" not in b["brand"] for b in meta["brands"])
