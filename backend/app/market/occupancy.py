"""Ước tính công suất của một khách sạn trên một kênh từ số phòng còn (hàm thuần).

Tồn phòng nhìn thấy (inventory) của mỗi loại phòng = lớn nhất từng thấy gần đây (số chính xác hoặc
mức sàn "ít nhất N"): là cận dưới của phân bổ trên OTA, không phải tổng phòng khách sạn. Mỗi lần
quét cho một khoảng phòng còn, nên công suất là khoảng [thấp, cao] kèm độ phủ (phần inventory biết
chắc). Không đoán số khi kênh không lộ: độ phủ thấp thì giao diện không hiện con số.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import StockConfidence

Q4 = Decimal("0.0001")
MIN_COVERAGE = Decimal("0.5")  # dưới mức này giao diện nói "không đủ số", không hiện công suất
MAX_WIDTH = Decimal("0.2")  # khoảng [thấp, cao] rộng hơn 20 điểm thì điểm giữa là nhiễu


def is_reliable(coverage: Decimal, occ_low: Decimal, occ_high: Decimal) -> bool:
    """Đủ tin để hiện "≈X%" và dùng cho nhịp/gợi ý: biết chắc ≥ 50% và khoảng hẹp ≤ 20 điểm."""
    return coverage >= MIN_COVERAGE and occ_high - occ_low <= MAX_WIDTH


@dataclass(frozen=True)
class RoomState:
    room_type_id: int
    confidence: str  # exact | capped | hidden | sold_out
    rooms_left: int | None
    dropdown_max: int | None = None

    @property
    def floor(self) -> int | None:
        """Số phòng còn chắc chắn có: số chính xác, hoặc mức sàn khi "ít nhất N"."""
        if self.confidence == StockConfidence.EXACT:
            return self.rooms_left
        if self.confidence == StockConfidence.CAPPED:
            return self.rooms_left if self.rooms_left is not None else self.dropdown_max
        return None


@dataclass(frozen=True)
class OccEstimate:
    inventory: int
    left_low: int
    left_high: int
    coverage: Decimal  # 0..1

    @property
    def occ_low(self) -> Decimal:
        return (1 - Decimal(self.left_high) / Decimal(self.inventory)).quantize(Q4)

    @property
    def occ_high(self) -> Decimal:
        return (1 - Decimal(self.left_low) / Decimal(self.inventory)).quantize(Q4)

    @property
    def occ_mid(self) -> Decimal:
        return ((self.occ_low + self.occ_high) / 2).quantize(Q4, ROUND_HALF_UP)

    @property
    def reliable(self) -> bool:
        return is_reliable(self.coverage, self.occ_low, self.occ_high)


def inventory_from(observations: Iterable[RoomState]) -> dict[int, int]:
    """Tồn phòng nhìn thấy mỗi loại phòng: lớn nhất trong các số chính xác và mức sàn đã thấy."""
    inv: dict[int, int] = {}
    for r in observations:
        f = r.floor
        if f is not None and f > 0:
            inv[r.room_type_id] = max(inv.get(r.room_type_id, 0), f)
    return inv


def estimate(
    status: str,
    rooms: Iterable[RoomState],
    inventory: dict[int, int],
    rooms_total: int | None = None,
) -> OccEstimate | None:
    """Công suất một (khách sạn, kênh, đêm) ở một lần quét.

    - `unknown` (bị chặn, lỗi) hoặc chưa biết inventory: None.
    - Hết phòng: mọi loại phòng còn 0 (có thể là đóng bán, giao diện ghi rõ).
    - Loại phòng có inventory mà lần này không bán: còn 0 (đã bán hết hoặc đóng).
    - Chính xác: biết chắc. "Ít nhất N": [N, inventory]. Ẩn số: [1, inventory].
    """
    total = sum(v for v in inventory.values() if v > 0)
    if status not in ("available", "sold_out") or total == 0:
        return None
    # Tổng phòng công bố/người dùng nhập (5.6): mẫu số là tổng phòng của khách sạn khi lớn hơn
    # phần kênh từng mở bán — "lớn nhất từng thấy" là cận dưới và làm công suất ra cao.
    denom = max(total, rooms_total or 0)
    if status == "sold_out":
        return OccEstimate(denom, 0, 0, Decimal(1))
    by_type = {r.room_type_id: r for r in rooms}
    if not by_type:
        # "Còn phòng" mà không đọc được loại phòng nào (parse lỗi một phần): không suy ra là hết.
        return None
    low = high = known = 0
    for rt, inv in inventory.items():
        if inv <= 0:
            continue
        r = by_type.get(rt)
        if r is None or r.confidence == StockConfidence.SOLD_OUT:
            known += inv
            continue
        if r.confidence == StockConfidence.EXACT and r.rooms_left is not None:
            left = min(r.rooms_left, inv)
            low, high, known = low + left, high + left, known + inv
        elif r.confidence == StockConfidence.CAPPED and r.floor is not None:
            low, high = low + min(r.floor, inv), high + inv
        else:  # ẩn số: còn ít nhất 1
            low, high = low + 1, high + inv
    return OccEstimate(denom, low, high, (Decimal(known) / Decimal(total)).quantize(Q4))
