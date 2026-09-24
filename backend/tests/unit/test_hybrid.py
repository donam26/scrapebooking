import json
from datetime import UTC, datetime, timedelta

from app.clock import FixedClock
from app.collector.booking.hybrid import HybridCollector
from app.collector.fake import FakeCollector
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import SessionManager
from app.domain.models import HotelRef, ProbeMethod, ProbeStatus
from tests.fakes import FakeBootstrapper, FakeFetcher, any_date, fake_parser, no_sleep, resp

HOTEL = HotelRef(1, "vn", "vn/x", "https://www.booking.com/hotel/vn/x.html")


def _build(
    fetcher: FakeFetcher, fallback: FakeCollector | None = None
) -> tuple[HybridCollector, FakeBootstrapper]:
    boot = FakeBootstrapper()
    sessions = SessionManager(
        bootstrapper=boot,
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        max_age=timedelta(minutes=20),
        max_requests=100,
        clock=FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC)),
    )
    limiter = RateLimiter(min_interval=0, jitter=0, sleep=no_sleep)
    collector = HybridCollector(
        sessions=sessions,
        fetcher=fetcher,
        limiter=limiter,
        fallback=fallback,
        parser=fake_parser,
        backoff=no_sleep,
        http_retries=1,
    )
    return collector, boot


async def test_ok_page() -> None:
    fetcher = FakeFetcher(resp(200, "<html>ROOMS</html>"))
    collector, boot = _build(fetcher)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert r.method == ProbeMethod.HTTP
    assert r.offers[0].booking_room_id == "101"
    assert r.raw_html == "<html>ROOMS</html>"
    assert r.http_status == 200
    assert r.booking_hotel_id == "555"
    assert len(boot.calls) == 1
    url, _ = fetcher.get_calls[0]
    assert "checkin=2026-10-05&checkout=2026-10-06" in url
    assert "selected_currency=VND" in url


async def test_sold_out_page() -> None:
    collector, _ = _build(FakeFetcher(resp(200, "<html>SOLDOUT</html>")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.SOLD_OUT


async def test_blocked_then_ok_on_fresh_session() -> None:
    fetcher = FakeFetcher(resp(403, ""), resp(200, "<html>ROOMS</html>"))
    collector, boot = _build(fetcher)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert len(boot.calls) == 2
    first_session = fetcher.get_calls[0][1]
    second_session = fetcher.get_calls[1][1]
    assert first_session != second_session
    assert fetcher.closed == [first_session]


async def test_blocked_twice_uses_fallback() -> None:
    fallback = FakeCollector()
    fallback.set_probe(HOTEL.id, any_date(), ProbeStatus.OK)
    fetcher = FakeFetcher(resp(403, ""), resp(429, ""))
    collector, boot = _build(fetcher, fallback)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert fallback.probe_calls == [(1, any_date(), 1, 2)]
    assert len(boot.calls) == 2


async def test_blocked_twice_without_fallback_is_blocked() -> None:
    collector, _ = _build(FakeFetcher(resp(403, ""), resp(403, "")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.BLOCKED
    assert r.http_status == 403


async def test_empty_page_goes_to_fallback() -> None:
    fallback = FakeCollector()
    fallback.set_probe(HOTEL.id, any_date(), ProbeStatus.NO_ROOMS_1N)
    collector, boot = _build(FakeFetcher(resp(200, "<html>nothing</html>")), fallback)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.NO_ROOMS_1N
    assert len(fallback.probe_calls) == 1
    assert len(boot.calls) == 1  # trang rỗng không thu hồi session


async def test_transport_error() -> None:
    collector, _ = _build(FakeFetcher(ConnectionError("boom")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    assert "boom" in (r.error or "")


async def test_not_found() -> None:
    collector, _ = _build(FakeFetcher(resp(404, "")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    assert r.http_status == 404


async def test_calendar_ok_sends_csrf() -> None:
    body = {
        "data": {
            "availabilityCalendar": {
                "hotelId": 1,
                "days": [
                    {
                        "checkin": "2026-10-05",
                        "available": True,
                        "minLengthOfStay": 1,
                        "avgPriceFormatted": "VND 1",
                    }
                ],
            }
        }
    }
    fetcher = FakeFetcher(resp(200, json.dumps(body)))
    collector, _ = _build(fetcher)
    cal = await collector.fetch_calendar(HOTEL, any_date(), 30, adults=2)
    assert cal.ok and cal.day(any_date()) is not None
    url, payload, headers, _ = fetcher.post_calls[0]
    assert url.startswith("https://www.booking.com/dml/graphql")
    assert payload["variables"]["input"]["pagename"] == "x"
    assert headers["x-booking-csrf-token"] == "csrf-1"


async def test_calendar_blocked_retires_session() -> None:
    fetcher = FakeFetcher(resp(403, ""))
    collector, boot = _build(fetcher)
    cal = await collector.fetch_calendar(HOTEL, any_date(), 30, adults=2)
    assert not cal.ok and cal.error == "blocked"
    assert fetcher.closed == [fetcher.post_calls[0][3]]
    assert len(boot.calls) == 1
