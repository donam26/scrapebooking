from datetime import date, timedelta

from app.domain.models import PageOutcome, ParsedPage, ProbeMethod, ProbeResult, ProbeStatus

_STATUS_BY_OUTCOME = {
    PageOutcome.ROOMS: ProbeStatus.OK,
    PageOutcome.SOLD_OUT: ProbeStatus.SOLD_OUT,
    PageOutcome.EMPTY: ProbeStatus.NO_ROOMS_1N,
}


def probe_result_from_page(
    page: ParsedPage,
    *,
    method: ProbeMethod,
    checkin: date,
    nights: int,
    adults: int,
    raw_html: str | None,
    http_status: int | None,
    session_id: str | None,
    duration_ms: int,
) -> ProbeResult:
    return ProbeResult(
        status=_STATUS_BY_OUTCOME[page.outcome],
        method=method,
        checkin=checkin,
        checkout=checkin + timedelta(days=nights),
        nights=nights,
        adults=adults,
        offers=page.offers,
        raw_html=raw_html,
        http_status=http_status,
        session_id=session_id,
        duration_ms=duration_ms,
        booking_hotel_id=page.booking_hotel_id,
        hotel_name=page.hotel_name,
    )


def failed_result(
    status: ProbeStatus,
    *,
    method: ProbeMethod,
    checkin: date,
    nights: int,
    adults: int,
    error: str,
    http_status: int | None = None,
    session_id: str | None = None,
    duration_ms: int = 0,
    raw_html: str | None = None,
) -> ProbeResult:
    return ProbeResult(
        status=status,
        method=method,
        checkin=checkin,
        checkout=checkin + timedelta(days=nights),
        nights=nights,
        adults=adults,
        offers=(),
        raw_html=raw_html,
        http_status=http_status,
        session_id=session_id,
        duration_ms=duration_ms,
        error=error,
    )
