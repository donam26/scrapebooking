from datetime import date, timedelta

from app.domain.models import (
    CalendarResult,
    ListingRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RoomOffer,
)


class FakeCollector:
    """Collector kịch bản sẵn cho test worker."""

    def __init__(self) -> None:
        self._calendars: dict[tuple[int, int], CalendarResult] = {}  # (hotel, nbRooms)
        self._probes: dict[tuple[int, date], ProbeResult] = {}
        # Kịch bản theo cả số đêm (VD probe bắc cầu 2 đêm từ hôm trước), ưu tiên hơn `_probes`.
        self._stay_probes: dict[tuple[int, date, int], ProbeResult] = {}
        self.probe_calls: list[tuple[int, date, int, int]] = []
        self.calendar_calls: list[tuple[int, date, int, int]] = []  # (hotel, start, days, rooms)

    def set_calendar(self, hotel_id: int, result: CalendarResult, rooms: int = 1) -> None:
        self._calendars[(hotel_id, rooms)] = result

    def set_probe(
        self,
        hotel_id: int,
        checkin: date,
        status: ProbeStatus,
        offers: tuple[RoomOffer, ...] = (),
        nights: int = 1,
        raw_html: str | None = "<html>fake</html>",
    ) -> None:
        self._probes[(hotel_id, checkin)] = self._scripted(
            checkin, status, offers, nights, raw_html
        )

    @staticmethod
    def _scripted(
        checkin: date,
        status: ProbeStatus,
        offers: tuple[RoomOffer, ...],
        nights: int,
        raw_html: str | None,
    ) -> ProbeResult:
        return ProbeResult(
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
            external_id="999",
            hotel_name="Fake Hotel",
        )

    def set_stay_probe(
        self,
        hotel_id: int,
        checkin: date,
        nights: int,
        status: ProbeStatus,
        offers: tuple[RoomOffer, ...] = (),
    ) -> None:
        self._stay_probes[(hotel_id, checkin, nights)] = self._scripted(
            checkin, status, offers, nights, "<html>fake</html>"
        )

    async def fetch_calendar(
        self, hotel: ListingRef, start: date, days: int, adults: int, rooms: int = 1
    ) -> CalendarResult:
        self.calendar_calls.append((hotel.id, start, days, rooms))
        return self._calendars.get(
            (hotel.id, rooms), CalendarResult(ok=False, error="not scripted")
        )

    async def probe(
        self, hotel: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        self.probe_calls.append((hotel.id, checkin, nights, adults))
        scripted = self._stay_probes.get((hotel.id, checkin, nights)) or self._probes.get(
            (hotel.id, checkin)
        )
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
