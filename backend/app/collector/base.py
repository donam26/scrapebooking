from datetime import date
from typing import Protocol

from app.domain.models import (
    CalendarResult,
    ListingCandidate,
    ListingIdentity,
    ListingQuery,
    ListingRef,
    ProbeResult,
)


class Collector(Protocol):
    """Thu dữ liệu một listing. Mỗi kênh một cài đặt (app/collector/<kênh>/)."""

    async def fetch_calendar(
        self, listing: ListingRef, start: date, days: int, adults: int
    ) -> CalendarResult: ...

    async def probe(
        self, listing: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult: ...


class ListingVerifier(Protocol):
    """Kiểm tra URL listing trỏ đúng một khách sạn: tên, id của kênh, toạ độ (D8)."""

    async def verify(self, listing: ListingRef) -> ListingIdentity: ...


class ListingFinder(Protocol):
    """Tìm cùng khách sạn trên kênh này theo tên/thành phố/toạ độ (API gợi ý của kênh)."""

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]: ...


class ListingNotFound(Exception):
    """verify(): kênh nói rõ listing không tồn tại — CHỈ khi HTTP 404 thật hoặc mã "không tồn tại"
    riêng của kênh (Mytour 4103, Agoda payload đầy đủ mà không có khách sạn). Worker đếm chuỗi
    not_found (`listings.not_found_count`); đủ ngưỡng mới đánh `broken`. Probe báo cùng nghĩa bằng
    `ProbeStatus.ERROR` + `error="not_found"`."""


class ListingBlocked(Exception):
    """verify()/suggest(): bị chống bot chặn, thử lại sau (listing giữ trạng thái chờ). Gồm cả
    trang 200 thiếu cấu trúc mong đợi (challenge, chuyển hướng, JSON cụt): chặn mềm → thu hồi
    session, không bao giờ coi là "không tồn tại"."""
