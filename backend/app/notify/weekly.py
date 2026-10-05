"""Báo cáo tuần (hàm thuần): 7 ngày qua của đối thủ và 14 đêm tới của bạn.

Chỉ tổng hợp số đã có (sự kiện, chỉ số thị trường, ngày lễ); không suy đoán nhu cầu.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.analytics.compset import CompsetDay
from app.holidays.data import Holiday

COUNTED = ("sold_out", "low_stock_enter", "price_down", "price_up")
TIGHT_SHARE = Decimal("0.5")
OUTLOOK_NIGHTS = 14


@dataclass(frozen=True)
class WeekEvent:
    hotel_name: str
    event_type: str
    room_level: bool  # sự kiện mức loại phòng (sắp hết phòng); giá/hết phòng tính ở mức khách sạn


@dataclass(frozen=True)
class WeeklyReport:
    past_start: date
    past_end: date
    outlook_start: date
    outlook_end: date
    counts: dict[str, int] = field(default_factory=dict)
    busiest: tuple[str, int] | None = None
    tight_nights: list[tuple[date, int, int]] = field(default_factory=list)
    vs_median_avg: int | None = None
    vs_median_low: tuple[date, int] | None = None
    vs_median_high: tuple[date, int] | None = None
    holidays: list[tuple[date, str]] = field(default_factory=list)
    nights_with_data: int = 0

    @property
    def empty(self) -> bool:
        return not any(self.counts.values()) and self.nights_with_data == 0


def build_weekly_report(
    today: date, events: list[WeekEvent], compset: list[CompsetDay], holidays: list[Holiday]
) -> WeeklyReport:
    counts = Counter(
        e.event_type
        for e in events
        if e.event_type in COUNTED and (e.room_level == (e.event_type == "low_stock_enter"))
    )
    per_hotel = Counter(e.hotel_name for e in events if e.event_type in COUNTED)
    busiest = per_hotel.most_common(1)[0] if per_hotel else None

    end = today + timedelta(days=OUTLOOK_NIGHTS - 1)
    window = [c for c in compset if today <= c.stay_date <= end]
    tight = [
        (c.stay_date, c.competitors_sold_out, c.competitors_observed)
        for c in window
        if c.sold_out_share is not None and c.sold_out_share >= TIGHT_SHARE
    ]
    tight.sort(key=lambda t: (-t[1] / max(t[2], 1), t[0]))
    deltas = [
        (c.stay_date, int((c.price_index - 100).quantize(Decimal(1))))
        for c in window
        if c.price_index is not None
    ]
    return WeeklyReport(
        past_start=today - timedelta(days=7),
        past_end=today - timedelta(days=1),
        outlook_start=today,
        outlook_end=end,
        counts={k: counts.get(k, 0) for k in COUNTED},
        busiest=busiest,
        tight_nights=tight[:3],
        vs_median_avg=round(sum(d for _, d in deltas) / len(deltas)) if deltas else None,
        vs_median_low=min(deltas, key=lambda t: t[1]) if deltas else None,
        vs_median_high=max(deltas, key=lambda t: t[1]) if deltas else None,
        holidays=[(h.date, h.name) for h in holidays if today <= h.date <= end],
        nights_with_data=sum(1 for c in window if c.competitors_observed > 0),
    )
