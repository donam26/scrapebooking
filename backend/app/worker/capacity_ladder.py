"""Thang nbRooms: đo tổng phòng còn của cả khách sạn trên Booking.com, vượt trần 10/loại phòng.

Trang khách sạn chỉ cho mỗi loại phòng tới 10 ("≥10"). Lịch GraphQL `AvailabilityCalendar` với
`nbRooms = N` (1 người lớn/phòng) trả lời cho MỌI đêm trong cửa sổ: "khách sạn còn bán được N phòng
cùng lúc?" — tính trên tổng các loại phòng (kiểm live 16/10/2026: Reverie trang Σ 14 nhưng còn ở
N = 15; Caravelle còn ở N = 100; N = 120 → lỗi 500). Mỗi nấc là MỘT request cho cả cửa sổ đêm.

Chạy sau vòng probe của run: nấc tăng dần, bỏ nấc khi mọi đêm đã biết sàn ≥ N (từ trang) hoặc đã có
trần. Kết quả ghi vào `hotel_calendars.rooms_min/rooms_max`; analytics gộp với số của trang. Lịch
được ưu tiên hơn tổng của trang (trang tìm 2 người lớn có thể thiếu loại phòng), nên cần nấc nhỏ
2–4 để vẫn chốt được "còn đúng 2" ở đêm sắp kín.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.analytics.rooms_left_bounds import hotel_bounds
from app.collector.base import Collector
from app.domain.models import ListingRef
from app.logging import get_logger
from app.repo.snapshots import SnapshotRepository

log = get_logger(__name__)


@dataclass
class Ladder:
    """`floors`: sàn phòng còn mỗi đêm theo trang (đêm còn bán trong run). `lo`: nấc lớn nhất lịch
    xác nhận còn; `hi`: trần (nấc nhỏ nhất lịch báo không còn, trừ 1)."""

    floors: dict[date, int]
    lo: dict[date, int] = field(default_factory=dict)
    hi: dict[date, int] = field(default_factory=dict)

    def needs(self, n: int) -> list[date]:
        """Đêm mà nấc N còn cho thêm thông tin: chưa có trần và sàn đã biết < N."""
        return sorted(
            d
            for d, floor in self.floors.items()
            if d not in self.hi and max(floor, self.lo.get(d, 0)) < n
        )

    def apply(self, n: int, available: Mapping[date, bool]) -> None:
        for d in self.needs(n):
            answer = available.get(d)
            if answer is True:
                self.lo[d] = n
            elif answer is False:
                self.hi[d] = n - 1

    def bounds(self) -> dict[date, tuple[int | None, int | None]]:
        """(rooms_min, rooms_max) của các đêm lịch đã trả lời ít nhất một nấc."""
        return {
            d: (self.lo.get(d), self.hi.get(d))
            for d in sorted(self.floors)
            if d in self.lo or d in self.hi
        }


async def run_capacity_ladder(
    collector: Collector,
    snapshots: SnapshotRepository,
    listing: ListingRef,
    scan_run_id: int,
    rungs: Sequence[int],
) -> int:
    """Đo các nấc cho những đêm còn bán của run (có hàng lịch), ghi kết quả. Trả số request lịch.
    Lịch lỗi/bị chặn ở một nấc: dừng thang, giữ những nấc đã đo."""
    states = await snapshots.room_states_by_date(scan_run_id, listing.hotel_id)
    measurable = await snapshots.calendar_dates(scan_run_id, listing.hotel_id)
    floors: dict[date, int] = {}
    for d, rooms in states.items():
        b = hotel_bounds(rooms)
        if d in measurable and b is not None:
            floors[d] = b.min
    ladder = Ladder(floors)
    requests = 0
    for n in sorted(set(rungs)):
        dates = ladder.needs(n)
        if not dates:
            continue
        days = (dates[-1] - dates[0]).days + 1
        requests += 1
        try:
            cal = await collector.fetch_calendar(listing, dates[0], days, n, rooms=n)
        except Exception:  # noqa: BLE001 — giữ các nấc đã đo (VD hết ngân sách request)
            log.exception("capacity_ladder_raised", hotel_id=listing.hotel_id, rung=n)
            break
        if not cal.ok:
            log.warning(
                "capacity_ladder_stopped", hotel_id=listing.hotel_id, rung=n, error=cal.error
            )
            break
        ladder.apply(n, {day.checkin: day.available for day in cal.days})
    await snapshots.set_capacity_bounds(scan_run_id, listing.hotel_id, ladder.bounds())
    return requests
