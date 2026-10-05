"""Thống kê giá danh sách (thuần): trung bình, tứ phân vị, histogram theo khoảng giá VND cố định."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# 8 khoảng: <500k, 500k–1tr, 1–1,5tr, 1,5–2tr, 2–3tr, 3–5tr, 5–10tr, ≥10tr (VND/đêm).
BUCKET_EDGES = tuple(
    Decimal(x)
    for x in (0, 500_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000)
)


@dataclass(frozen=True)
class PriceBucket:
    lo: Decimal
    hi: Decimal | None  # None: khoảng cuối, không chặn trên
    count: int


@dataclass(frozen=True)
class PriceStats:
    count: int
    avg: Decimal | None
    median: Decimal | None
    p25: Decimal | None
    p75: Decimal | None
    min: Decimal | None
    max: Decimal | None
    histogram: list[PriceBucket]


def _whole(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def percentile(sorted_values: list[Decimal], q: Decimal) -> Decimal | None:
    """Nội suy tuyến tính giữa hai hạng gần nhất (như numpy mặc định); q trong [0, 1]."""
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def histogram(values: list[Decimal]) -> list[PriceBucket]:
    edges = list(BUCKET_EDGES)
    counts = [0] * len(edges)
    for v in values:
        i = max(j for j, edge in enumerate(edges) if v >= edge) if v >= edges[0] else 0
        counts[i] += 1
    return [
        PriceBucket(lo=edge, hi=edges[i + 1] if i + 1 < len(edges) else None, count=counts[i])
        for i, edge in enumerate(edges)
    ]


def price_stats(values: list[Decimal]) -> PriceStats:
    ordered = sorted(values)
    if not ordered:
        return PriceStats(0, None, None, None, None, None, None, histogram([]))

    def pct(q: str) -> Decimal | None:
        p = percentile(ordered, Decimal(q))
        return _whole(p) if p is not None else None

    return PriceStats(
        count=len(ordered),
        avg=_whole(sum(ordered, Decimal(0)) / len(ordered)),
        median=pct("0.5"),
        p25=pct("0.25"),
        p75=pct("0.75"),
        min=ordered[0],
        max=ordered[-1],
        histogram=histogram(ordered),
    )
