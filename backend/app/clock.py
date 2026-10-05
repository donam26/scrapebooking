from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Múi giờ mặc định theo nước khách sạn: dữ liệu quan sát (metrics, occupancy) dùng chung giữa tenant
# nên không lấy múi giờ tenant được; lấy theo nước của khách sạn.
COUNTRY_TIMEZONES: dict[str, str] = {
    "vn": "Asia/Ho_Chi_Minh",
    "th": "Asia/Bangkok",
    "sg": "Asia/Singapore",
    "my": "Asia/Kuala_Lumpur",
    "id": "Asia/Jakarta",
    "ph": "Asia/Manila",
    "kh": "Asia/Phnom_Penh",
    "la": "Asia/Vientiane",
    "jp": "Asia/Tokyo",
    "kr": "Asia/Seoul",
    "us": "America/New_York",
    "gb": "Europe/London",
}


def country_timezone(country_code: str | None) -> str:
    return COUNTRY_TIMEZONES.get((country_code or "").lower(), "UTC")


def local_date(at: datetime, timezone: str) -> date:
    """Ngày địa phương của tenant tại thời điểm `at` (UTC). Múi giờ hỏng trong DB cũ → UTC.

    Dùng cho mọi phép "số ngày tới khi đến" (days_to_arrival): mốc quét 06:00 giờ Việt Nam là
    23:00 UTC hôm trước, lấy ngày UTC sẽ lệch một ngày so với mốc 14:00/22:00 cùng ngày."""
    try:
        return at.astimezone(ZoneInfo(timezone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return at.astimezone(UTC).date()


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FixedClock:
    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, **kwargs: float) -> None:
        self._at = self._at + timedelta(**kwargs)
