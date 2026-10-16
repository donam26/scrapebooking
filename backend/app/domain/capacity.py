"""Sức chứa của khách sạn trên Booking.com (thuần): gợi ý "Số phòng" khi người dùng chưa nhập.

Booking không công bố tổng số phòng (16/10/2026: trang đầy đủ của 5 khách sạn thật không có trường
nào, mô tả của khách sạn cũng không nhắc). Thứ đo được là số ĐƠN VỊ Booking bán cùng lúc trong một
đêm (lịch `nbRooms`, app/worker/capacity_probe.py): thường bằng số phòng khi khách sạn đưa hết phòng
lên Booking; nhỏ hơn khi khách sạn giữ phòng cho kênh khác; LỚN hơn khi Booking bán giường dorm
(Meander Saigon: 42 phòng, Booking bán 94 đơn vị).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Lịch GraphQL nhận nbRooms tới 100; 110 và 120 → lỗi 500 (kiểm live 16/10/2026). Còn bán ở 100
# nghĩa là khách sạn có thể lớn hơn nhiều (Reverie 286 phòng): chỉ là cận dưới.
CAPACITY_CEILING = 100

# Loại phòng bán theo giường: tên trên Booking luôn có "Dormitory"/"Dorm" ("Bed in 8-Bed Mixed
# Dormitory Room", "Single Bed in Female Dormitory Room") hoặc là khoang ngủ ("Capsule"). Không bắt
# "Bed in" chung chung ("Sofa Bed in Living Room", "Extra Bed in the Room") hay "Dormer".
_BED_UNIT_RE = re.compile(
    r"\bdorm(?:s|itory|itories)?\b|\bcapsule\b|phòng\s+(?:ngủ\s+)?tập\s+thể|ký\s+túc\s+xá",
    re.IGNORECASE,
)


def sells_beds(room_type_names: Iterable[str]) -> bool:
    """Booking bán giường dorm của khách sạn này (số đơn vị đo được đếm cả giường)."""
    return any(_BED_UNIT_RE.search(name) for name in room_type_names)


@dataclass(frozen=True)
class RoomsSuggestion:
    rooms: int  # số phòng (đơn vị) Booking bán nhiều nhất trong một đêm
    # Chỉ biết "≥ rooms": chạm trần đo, hoặc lượt quét thường từng thấy nhiều hơn kết quả đo đêm xa
    # (VD khách sạn giới hạn số phòng mỗi lần đặt, cửa sổ xa mới mở bán một phần).
    lower_bound: bool
    capped: bool  # chạm trần đo 100: khách sạn lớn
    includes_beds: bool  # có giường dorm: con số lớn hơn số phòng thật

    @property
    def confirmable(self) -> bool:
        """Dùng được làm "Số phòng" bằng một nút bấm: số đo đúng, không phải cận dưới, không
        đếm giường. Còn lại người dùng nhập số phòng công bố."""
        return not self.lower_bound and not self.includes_beds


def rooms_suggestion(
    capacity_max: int | None,
    capacity_capped: bool,
    rooms_max_seen: int | None,
    *,
    measured: bool,
    includes_beds: bool,
) -> RoomsSuggestion | None:
    """Gợi ý = số lớn nhất Booking từng bán trong một đêm, chỉ khi đã đo xong các đêm xa
    (`measured`) VÀ cửa sổ đó có phòng (`capacity_max`). Sàn phòng còn của các đêm gần
    (`rooms_max_seen`) một mình không đủ: các đêm đó đã bán bớt nên có thể thấp xa số thật
    (Reverie: sàn 62, đêm xa còn ≥100); nó chỉ nâng con số và biến gợi ý thành cận dưới khi lớn hơn
    kết quả đo."""
    if not measured or not capacity_max:
        return None
    seen = rooms_max_seen or 0
    rooms = max(capacity_max, seen)
    capped = capacity_capped or rooms >= CAPACITY_CEILING
    return RoomsSuggestion(
        rooms=rooms,
        lower_bound=capped or seen > capacity_max,
        capped=capped,
        includes_beds=includes_beds,
    )
