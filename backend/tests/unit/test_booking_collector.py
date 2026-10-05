"""BookingCollector.verify/search_page với fetcher giả: trang 200 không có dữ liệu khách sạn là chặn
mềm (BLOCKED, thu hồi session), chỉ 404 thật mới là not_found; session thu hồi đóng client."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.clock import FixedClock
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.booking.collector import BookingCollector
from app.collector.factory import CollectorDeps
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from tests.fakes import FakeBootstrapper, FakeFetcher, booking_listing, no_sleep, resp

HOTEL = booking_listing(slug="vn/meander-saigon")


def _collector(fetcher: FakeFetcher) -> tuple[BookingCollector, RateLimiter]:
    limiter = RateLimiter(min_interval=0, jitter=0, sleep=no_sleep)
    deps = CollectorDeps(
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        clock=FixedClock(datetime(2026, 10, 1, 8, 0, tzinfo=UTC)),
        limiter=limiter,
        currency="VND",
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=400,
    )
    return BookingCollector(deps, fetcher=fetcher, bootstrapper=FakeBootstrapper()), limiter


async def test_verify_reads_identity_from_hotel_page(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "booking" / "meander_identity.html").read_text(encoding="utf-8")
    fetcher = FakeFetcher(resp(200, html))
    collector, _ = _collector(fetcher)
    identity = await collector.verify(HOTEL)
    assert identity.name and identity.external_id
    assert fetcher.get_calls[0][0].endswith("/hotel/vn/meander-saigon.en-gb.html")
    assert fetcher.closed == []


async def test_verify_200_challenge_page_is_blocked_not_broken() -> None:
    fetcher = FakeFetcher(resp(200, "<html><body><h1>Please wait a moment</h1></body></html>"))
    collector, limiter = _collector(fetcher)
    with pytest.raises(ListingBlocked, match="no hotel data"):
        await collector.verify(HOTEL)
    sid = fetcher.get_calls[0][1]
    assert fetcher.closed == [sid]  # session thu hồi → client đóng qua hook
    assert sid not in limiter._last


async def test_verify_not_found_only_on_real_404() -> None:
    collector, _ = _collector(FakeFetcher(resp(404, "<html>not found</html>")))
    with pytest.raises(ListingNotFound):
        await collector.verify(HOTEL)


async def test_search_page_without_result_markers_is_blocked() -> None:
    fetcher = FakeFetcher(resp(200, "<html><body>Pardon Our Interruption</body></html>"))
    collector, _ = _collector(fetcher)
    with pytest.raises(ListingBlocked):
        await collector.search_page("https://www.booking.com/searchresults.en-gb.html?x=1")
    assert fetcher.closed == [fetcher.get_calls[0][1]]
