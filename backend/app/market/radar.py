"""Radar cạnh tranh từ dữ liệu đã thu (roadmap Phase 4, BC N1–N3, N6) — hàm thuần, không I/O.

- Khuyến mãi: nhãn KM, độ sâu (so giá gạch) theo đối thủ × đêm; KM Booking tự áp hay KS bật.
- Hạn chế bán: số đêm tối thiểu, không nhận khách ngày đến.
- Chính sách huỷ: % đêm có gói hoàn huỷ, mức giảm của gói không hoàn huỷ so với gói linh hoạt.
- Khan phòng khu vực: số chỗ ở còn phòng kênh báo theo đêm, so cùng đêm 7 ngày trước.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.analytics.rules import median


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v is not None else None
    except (InvalidOperation, ValueError):
        return None


# ---- 4.1 khuyến mãi ---------------------------------------------------------------------------

# Chương trình do Booking.com tự áp (thành viên Genius, giá chỉ trên app) và mã giảm giá kiểu
# coupon (chữ in hoa + số, không khoảng trắng); còn lại là deal khách sạn bật trên extranet
# (Early Bird, Last-minute, Late Escape, Getaway, Limited-time, Black Friday…).
_COUPON_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{3,}$")
_CHANNEL_PROMO_WORDS = ("genius", "mobile", "app only", "chỉ trên app", "coupon", "voucher")


def promo_origin(label: str | None) -> Literal["channel", "hotel"] | None:
    """KM do kênh tự áp hay do khách sạn bật."""
    if not label:
        return None
    text = label.strip()
    if _COUPON_RE.match(text) or any(w in text.lower() for w in _CHANNEL_PROMO_WORDS):
        return "channel"
    return "hotel"


@dataclass
class PromoRun:
    label: str
    origin: str | None  # channel | hotel
    nights: list[date] = field(default_factory=list)
    max_depth_pct: Decimal | None = None
    started_at: datetime | None = None  # sự kiện promo_start sớm nhất còn trong cửa sổ


def promo_runs(
    promos_by_night: Mapping[date, Mapping[str, Any] | None],
    starts: Mapping[str, datetime] | None = None,
) -> list[PromoRun]:
    """KM đang chạy của một khách sạn: gộp theo nhãn, danh sách đêm áp dụng, độ sâu lớn nhất."""
    runs: dict[str, PromoRun] = {}
    for d in sorted(promos_by_night):
        for label, depth in (promos_by_night[d] or {}).items():
            run = runs.setdefault(label, PromoRun(label, promo_origin(label)))
            run.nights.append(d)
            dep = _dec(depth)
            if dep is not None and (run.max_depth_pct is None or dep > run.max_depth_pct):
                run.max_depth_pct = dep
    for label, run in runs.items():
        run.started_at = (starts or {}).get(label)
    return sorted(runs.values(), key=lambda r: (-(len(r.nights)), r.label))


def promo_share_by_night(
    hotels: Iterable[Mapping[date, Mapping[str, Any] | None]], nights: list[date]
) -> dict[date, tuple[int, int]]:
    """(số đối thủ đang chạy KM, số đối thủ có quan sát) mỗi đêm."""
    out: dict[date, list[int]] = {d: [0, 0] for d in nights}
    for h in hotels:
        for d in nights:
            if d in h:
                out[d][1] += 1
                if h[d]:
                    out[d][0] += 1
    return {d: (a, b) for d, (a, b) in out.items()}


# ---- 4.3 chính sách huỷ ------------------------------------------------------------------------


@dataclass(frozen=True)
class CancellationProfile:
    nights_priced: int
    nights_with_refundable: int
    nights_with_nonrefundable: int
    # Trung vị mức giảm (%) của gói không hoàn huỷ so với gói hoàn huỷ cùng bữa sáng.
    nr_discount_pct: Decimal | None
    pairs: int

    @property
    def refundable_share(self) -> Decimal | None:
        if not self.nights_priced:
            return None
        return (Decimal(self.nights_with_refundable) / self.nights_priced).quantize(Decimal("0.01"))


def cancellation_profile(
    prices_by_night: Iterable[Mapping[str, Any] | None],
) -> CancellationProfile:
    """Từ `prices_by_key` ("hoàn huỷ|bữa sáng" → giá) của các đêm: tỷ lệ đêm có gói linh hoạt và mức
    giảm của gói không hoàn huỷ (RoomPriceGenie: thường 10–20%)."""
    priced = with_flex = with_nr = 0
    discounts: list[Decimal] = []
    for prices in prices_by_night:
        if not prices:
            continue
        p = {k: v for k, raw in prices.items() if (v := _dec(raw)) is not None and v > 0}
        if not p:
            continue
        priced += 1
        flex = {k.split("|", 1)[1]: v for k, v in p.items() if k.startswith("t|")}
        nr = {k.split("|", 1)[1]: v for k, v in p.items() if k.startswith("f|")}
        with_flex += bool(flex)
        with_nr += bool(nr)
        for meal in set(flex) & set(nr):
            if nr[meal] < flex[meal]:
                discounts.append(
                    ((flex[meal] - nr[meal]) / flex[meal] * 100).quantize(Decimal("0.1"))
                )
    m = median(discounts)
    return CancellationProfile(
        priced,
        with_flex,
        with_nr,
        m.quantize(Decimal("0.1")) if m is not None else None,
        len(discounts),
    )


# ---- 4.2 hạn chế -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Restriction:
    stay_date: date
    min_stay: int  # 1 = không hạn chế số đêm
    closed_to_arrival: bool  # lịch Booking không cho nhận phòng ngày này

    @property
    def any(self) -> bool:
        return self.min_stay > 1 or self.closed_to_arrival


def restriction_for(d: date, min_stay: int | None, status: str | None) -> Restriction:
    return Restriction(d, max(1, min_stay or 1), status == "restricted")


# ---- 4.4 khan phòng khu vực -------------------------------------------------------------------


@dataclass(frozen=True)
class AreaNight:
    stay_date: date
    properties: int | None  # số chỗ ở còn phòng kênh báo ở lần quét gần nhất
    scanned_at: datetime | None
    lead_days: int | None
    week_ago: int | None  # cùng đêm, lần quét gần nhất cách ≥7 ngày trước đó
    change_pct: Decimal | None


def area_scarcity(
    scans: Iterable[tuple[date, datetime, int | None]], nights: list[date]
) -> list[AreaNight]:
    """(đêm, lúc quét, số chỗ ở còn phòng) → mỗi đêm: số mới nhất và số cùng đêm 7 ngày trước."""
    by_night: dict[date, list[tuple[datetime, int]]] = defaultdict(list)
    for d, at, n in scans:
        if n is not None:
            by_night[d].append((at, n))
    out = []
    for d in nights:
        obs = sorted(by_night.get(d, []))
        if not obs:
            out.append(AreaNight(d, None, None, None, None, None))
            continue
        at, n = obs[-1]
        earlier = [(t, v) for t, v in obs if t <= at - timedelta(days=7)]
        week = earlier[-1][1] if earlier else None
        change = (
            (Decimal(n - week) / Decimal(week) * 100).quantize(Decimal("0.1")) if week else None
        )
        out.append(AreaNight(d, n, at, (d - at.date()).days, week, change))
    return out
