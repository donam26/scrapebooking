"""Chỉ số thang phòng trống của thị trường (thuần).

c(N) = số khách sạn trong khu vực (khớp phân khúc) còn bán được ≥ N phòng cùng lúc một đêm trên
Booking.com: nấc 1 là danh sách (1 phòng, 2 người lớn), nấc N ≥ 2 là tìm kiếm `nbRooms = N` (1 người
lớn/phòng, Booking kẹp ≤ 30). Mọi số là cận dưới của phòng Booking còn bán, không phải tồn kho.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from statistics import median
from typing import Any


def rung_counts(base: int | None, ladder: Mapping[str, Any] | None) -> dict[int, int]:
    """{N: c(N)} từ số còn phòng của danh sách (nấc 1) và JSON `ladder`; ép không tăng theo N bằng
    cách kẹp xuống nấc dưới: nấc N ≥ 2 hỏi 1 người lớn/phòng nên có thể hơn danh sách (2 người lớn)
    vài khách sạn chỉ còn phòng đơn (đo 16/10: 605 so với 604) — nấc 1 luôn bằng số còn phòng."""
    counts: dict[int, int] = {}
    if base is not None:
        counts[1] = base
    for key, value in (ladder or {}).items():
        available = value.get("available") if isinstance(value, Mapping) else None
        if str(key).isdigit() and isinstance(available, int):
            counts[int(key)] = available
    out: dict[int, int] = {}
    ceiling: int | None = None
    for n in sorted(counts):
        ceiling = counts[n] if ceiling is None else min(ceiling, counts[n])
        out[n] = ceiling
    return out


def rooms_floor(counts: Mapping[int, int]) -> int | None:
    """Sàn tổng phòng còn bán của thị trường: Σ (c(N_k) − c(N_k+1)) · N_k + c(N_max) · N_max."""
    rungs = sorted(counts)
    if not rungs:
        return None
    total = 0
    for i, n in enumerate(rungs):
        above = counts[rungs[i + 1]] if i + 1 < len(rungs) else 0
        total += max(0, counts[n] - above) * n
    return total


def tightness(counts: Mapping[int, int], at: int = 10) -> float | None:
    """Tỉ lệ khách sạn còn phòng vẫn bán được ≥ `at` phòng: thấp = thị trường căng."""
    base, deep = counts.get(1), counts.get(at)
    if not base or deep is None:
        return None
    return round(deep / base, 4)


def sold_out_share(available: int | None, base: int | None) -> float | None:
    """1 − còn phòng / mẫu số phân khúc (cận dưới khi mẫu số là số còn phòng lớn nhất từng thấy)."""
    if available is None or not base:
        return None
    return round(max(0.0, 1 - available / base), 4)


def hotel_range(rooms_min: int | None, rungs: Sequence[int]) -> tuple[int | None, int | None]:
    """(cận dưới, cận trên) phòng còn của một khách sạn từ nấc lớn nhất nó còn bán được: qua nấc N
    nhưng không qua nấc kế tiếp N' → [N, N' − 1]; qua nấc cao nhất → (N, None) = "≥ N"."""
    if not rooms_min:
        return None, None
    higher = [n for n in sorted({1, *rungs}) if n > rooms_min]
    return rooms_min, (higher[0] - 1 if higher else None)


def percentile_rank(values: Sequence[Decimal], x: Decimal) -> int | None:
    """Vị trí của `x` trong phân bố (0–100): tỉ lệ giá thấp hơn + nửa số bằng nhau."""
    if not values:
        return None
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return round(100 * (below + equal / 2) / len(values))


def median_or_none(values: Sequence[float]) -> float | None:
    return round(float(median(values)), 4) if values else None
