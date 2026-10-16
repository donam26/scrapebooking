"""Khoảng phòng còn của cả khách sạn trên Booking.com cho một đêm (hàm thuần).

Hai nguồn, gộp thành [min, max]:
- Trang khách sạn (tìm 2 người lớn): mỗi loại phòng là số chính xác, "ít nhất N" (dropdown chạm
  trần 10/loại) hoặc ẩn số. Tổng là sàn; chỉ khi mọi loại phòng chính xác mới có trần.
- Thang nbRooms của lịch GraphQL (worker/capacity_ladder.py): "khách sạn còn ≥ N phòng?" tính
  trên TỔNG mọi loại phòng (kể cả loại không hiện khi tìm 2 người), nên vừa nâng sàn vừa cho trần.

Chỉ nói "còn N phòng" khi min = max; còn lại giao diện ghi "≥min" hoặc "min–max".
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.models import StockConfidence


@dataclass(frozen=True)
class RoomsLeftBounds:
    min: int
    max: int | None  # None: không biết trần

    @property
    def exact(self) -> int | None:
        return self.min if self.max == self.min else None


def room_type_bounds(
    confidence: StockConfidence | str, rooms_left: int | None
) -> tuple[int, int | None]:
    """Khoảng của một loại phòng. Loại phòng đang được bán thì còn ít nhất 1."""
    if confidence == StockConfidence.SOLD_OUT:
        return 0, 0
    if confidence == StockConfidence.EXACT and rooms_left is not None:
        return rooms_left, rooms_left
    return max(rooms_left or 0, 1), None


def hotel_bounds(
    rooms: Iterable[tuple[StockConfidence | str, int | None]],
    *,
    sold_out: bool = False,
    calendar_min: int | None = None,
    calendar_max: int | None = None,
) -> RoomsLeftBounds | None:
    """`rooms`: (mức tin cậy, rooms_left) của các loại phòng đang bán. None khi không có loại phòng
    nào (trang không đọc được: không suy ra "hết")."""
    if sold_out:
        return RoomsLeftBounds(0, 0)
    pairs = [room_type_bounds(c, n) for c, n in rooms]
    if not pairs:
        return None
    floor = sum(lo for lo, _ in pairs)
    uppers = [hi for _, hi in pairs]
    ceiling = sum(hi for hi in uppers if hi is not None) if None not in uppers else None
    lo = max(floor, calendar_min or 0)
    hi = calendar_max if calendar_max is not None else ceiling
    if hi is not None and hi < lo:
        # Nguồn mâu thuẫn (thang lịch đo lúc khác, hoặc trang chỉ thấy loại phòng cho 2 người):
        # giữ sàn chắc chắn, bỏ trần.
        hi = None
    return RoomsLeftBounds(lo, hi)


def definitely_low(rooms_left_max: int | None, threshold: int) -> bool:
    """Chắc chắn còn ≤ ngưỡng (đối thủ "sắp hết"): cần biết trần. "≥N" không bao giờ là thấp."""
    return rooms_left_max is not None and rooms_left_max <= threshold
