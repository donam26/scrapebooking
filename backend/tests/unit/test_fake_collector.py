from datetime import date

from app.collector.fake import FakeCollector
from app.domain.models import CalendarDay, CalendarResult, HotelRef, ProbeStatus

HOTEL = HotelRef(1, "vn", "vn/x", "https://www.booking.com/hotel/vn/x.html")


async def test_fake_collector_scripts_and_records() -> None:
    fake = FakeCollector()
    fake.set_calendar(
        HOTEL.id, CalendarResult(ok=True, days=(CalendarDay(date(2026, 10, 1), True, 1, None),))
    )
    fake.set_probe(HOTEL.id, date(2026, 10, 1), ProbeStatus.OK)
    cal = await fake.fetch_calendar(HOTEL, date(2026, 10, 1), 30, adults=2)
    assert cal.ok
    r = await fake.probe(HOTEL, date(2026, 10, 1), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert fake.probe_calls == [(1, date(2026, 10, 1), 1, 2)]


async def test_fake_collector_default_is_error() -> None:
    fake = FakeCollector()
    r = await fake.probe(HOTEL, date(2026, 10, 9), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    cal = await fake.fetch_calendar(HOTEL, date(2026, 10, 1), 30, adults=2)
    assert not cal.ok
