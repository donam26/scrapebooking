from datetime import date
from typing import Protocol

from app.domain.models import CalendarResult, HotelRef, ProbeResult


class Collector(Protocol):
    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult: ...

    async def probe(
        self, hotel: HotelRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult: ...
