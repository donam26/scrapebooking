"""`BookingCollector.search_graphql`: phân loại phản hồi GraphQL `FullSearch` (chặn thật / trang
không phải JSON / lỗi đầu vào / 5xx) và lấy csrf khi session chưa có."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.clock import FixedClock
from app.collector.base import ListingBlocked
from app.collector.booking.collector import BookingCollector
from app.collector.factory import CollectorDeps
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import BootstrapResult, SessionManager
from tests.fakes import FakeBootstrapper, FakeFetcher, no_sleep, resp

SEARCH = "https://www.booking.com/searchresults.en-gb.html?dest_id=2088&dest_type=district"
OK = '{"data": {"searchQueries": {"search": {"results": []}}}}'


class NoCsrfBootstrapper(FakeBootstrapper):
    async def bootstrap(self, proxy: Any, warmup_url: str) -> BootstrapResult:
        r = await super().bootstrap(proxy, warmup_url)
        return BootstrapResult(r.cookies, r.user_agent, None, r.html)


def _collector(
    fetcher: FakeFetcher, boot: FakeBootstrapper | None = None
) -> tuple[BookingCollector, SessionManager]:
    clock = FixedClock(datetime(2026, 10, 16, 11, 0, tzinfo=UTC))
    proxies = StaticProxyProvider("http://u-{country}-{session}:p@h:1")
    deps = CollectorDeps(
        proxy_provider=proxies,
        clock=clock,
        limiter=RateLimiter(min_interval=0, jitter=0, sleep=no_sleep),
        currency="VND",
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=100,
    )
    sessions = SessionManager(
        bootstrapper=boot or FakeBootstrapper(),
        proxy_provider=proxies,
        max_age=timedelta(minutes=20),
        max_requests=100,
        clock=clock,
    )
    collector = BookingCollector.__new__(BookingCollector)
    collector._deps = deps
    collector._sessions = sessions
    collector._fetcher = fetcher  # type: ignore[assignment]
    return collector, sessions


async def test_ok_json_is_returned_with_session_csrf_and_search_headers() -> None:
    fetcher = FakeFetcher(resp(200, OK))
    collector, _ = _collector(fetcher)
    assert await collector.search_graphql({"operationName": "FullSearch"}, SEARCH) == OK
    url, _, headers, _ = fetcher.post_calls[0]
    assert url.startswith("https://www.booking.com/dml/graphql")
    assert headers["x-booking-csrf-token"] == "csrf-1" and headers["Referer"] == SEARCH
    assert headers["x-booking-context-action-name"] == "searchresults_irene"


@pytest.mark.parametrize(
    ("response", "retired"),
    [
        (resp(403, "denied"), True),  # chặn thật: thu hồi session
        (resp(200, "<html>challenge.js</html>"), True),  # challenge với mã 200
        (resp(200, "<html>not json</html>"), True),  # 200 không phải JSON
    ],
)
async def test_blocks_retire_the_session(response: Any, retired: bool) -> None:
    fetcher = FakeFetcher(response)
    collector, _ = _collector(fetcher)
    with pytest.raises(ListingBlocked):
        await collector.search_graphql({}, SEARCH)
    assert bool(fetcher.closed) is retired


@pytest.mark.parametrize("status", [400, 404, 422, 500, 502])
async def test_input_errors_and_5xx_are_plain_errors_not_blocks(status: int) -> None:
    fetcher = FakeFetcher(resp(status, '{"errors": []}'))
    collector, _ = _collector(fetcher)
    with pytest.raises(RuntimeError, match=f"http {status}") as info:
        await collector.search_graphql({}, SEARCH)
    assert not isinstance(info.value, ListingBlocked) and fetcher.closed == []


async def test_missing_csrf_is_read_from_search_page_or_home_page() -> None:
    page = '<html>b_csrf_token: "tok-page"; "nbResultsTotal": 1</html>'
    fetcher = FakeFetcher(resp(200, page), resp(200, OK))
    collector, _ = _collector(fetcher, NoCsrfBootstrapper())
    assert await collector.search_graphql({}, SEARCH) == OK
    assert fetcher.get_calls[0][0] == SEARCH
    assert fetcher.post_calls[0][2]["x-booking-csrf-token"] == "tok-page"

    # Khu vực toạ độ (Referer không có tham số tìm kiếm): lấy csrf ở trang chủ.
    home = '<html>"b_csrf_token":"tok-home"</html>'
    fetcher2 = FakeFetcher(resp(200, home), resp(200, OK))
    collector2, _ = _collector(fetcher2, NoCsrfBootstrapper())
    await collector2.search_graphql({}, "https://www.booking.com/searchresults.en-gb.html")
    assert fetcher2.get_calls[0][0] == "https://www.booking.com/"
    assert fetcher2.post_calls[0][2]["x-booking-csrf-token"] == "tok-home"


async def test_no_csrf_anywhere_is_a_block_and_nothing_is_posted() -> None:
    fetcher = FakeFetcher(resp(200, "<html>nbResultsTotal but no token</html>"))
    collector, _ = _collector(fetcher, NoCsrfBootstrapper())
    with pytest.raises(ListingBlocked, match="no csrf"):
        await collector.search_graphql({}, SEARCH)
    assert fetcher.post_calls == [] and fetcher.closed
