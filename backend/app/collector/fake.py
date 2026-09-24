from datetime import date, timedelta

from app.domain.models import (
    CalendarResult,
    HotelRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RoomOffer,
)


class FakeCollector:
    """Collector kịch bản sẵn cho test worker."""

    def __init__(self) -> None:
        self._calendars: dict[int, CalendarResult] = {}
        self._probes: dict[tuple[int, date], ProbeResult] = {}
        self.probe_calls: list[tuple[int, date, int, int]] = []
        self.calendar_calls: list[tuple[int, date, int]] = []

    def set_calendar(self, hotel_id: int, result: CalendarResult) -> None:
        self._calendars[hotel_id] = result

    def set_probe(
        self,
        hotel_id: int,
        checkin: date,
        status: ProbeStatus,
        offers: tuple[RoomOffer, ...] = (),
        nights: int = 1,
        raw_html: str | None = "<html>fake</html>",
    ) -> None:
        self._probes[(hotel_id, checkin)] = ProbeResult(
            status=status,
            method=ProbeMethod.HTTP,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=2,
            offers=offers,
            raw_html=raw_html,
            http_status=200,
            session_id="fake-session",
            duration_ms=1,
            booking_hotel_id="999",
            hotel_name="Fake Hotel",
        )

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        self.calendar_calls.append((hotel.id, start, days))
        return self._calendars.get(hotel.id, CalendarResult(ok=False, error="not scripted"))

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        self.probe_calls.append((hotel.id, checkin, nights, adults))
        scripted = self._probes.get((hotel.id, checkin))
        if scripted is None:
            return ProbeResult(
                status=ProbeStatus.ERROR,
                method=ProbeMethod.HTTP,
                checkin=checkin,
                checkout=checkin + timedelta(days=nights),
                nights=nights,
                adults=adults,
                offers=(),
                raw_html=None,
                http_status=None,
                session_id=None,
                duration_ms=0,
                error="not scripted",
            )
        return scripted
