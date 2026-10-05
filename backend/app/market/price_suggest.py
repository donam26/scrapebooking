"""Gợi ý giá theo luật cố định (hàm thuần), không tự đẩy giá.

Mỗi gợi ý kèm lý do là số liệu đã quan sát (đối thủ hết phòng, công suất ước tính, nhịp so cùng
kỳ, giá so trung vị), trả dạng mã + tham số (`Reason`); chữ dịch ở biên API bằng `reason_text`.
Ba loại:
- raise: bạn rẻ hơn trung vị trong khi thị trường căng → cân nhắc tăng về gần trung vị.
- hold: bạn đắt hơn trung vị nhưng thị trường đang bán tốt → chưa cần giảm.
- lower: đêm gần (≤ 7 ngày), bạn đắt hơn nhiều, thị trường không căng, bạn còn nhiều phòng.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.i18n import t

SOLD_SHARE_TIGHT = Decimal("0.5")
COMP_OCC_TIGHT = Decimal("0.85")
PACE_FAST = Decimal("0.15")


@dataclass(frozen=True)
class NightSignals:
    stay_date: date
    days_to_arrival: int
    own_status: str | None  # available | sold_out | unknown | None
    own_price: Decimal | None
    own_rooms_left: int | None  # số Booking báo chính xác
    own_occ: Decimal | None  # 0..1, ưu tiên PMS, sau đó ước tính đủ tin cậy
    comp_observed: int
    comp_sold_out: int
    comp_median_price: Decimal | None
    comp_occ: Decimal | None  # trung vị công suất ước tính đối thủ (đủ tin cậy)
    comp_pace: Decimal | None  # nhịp thị trường so cùng kỳ (điểm 0..1)
    holiday: str | None = None  # tên ngày lễ đã theo ngôn ngữ người xem


@dataclass(frozen=True)
class Reason:
    key: str  # khoá catalog `price.<key>`
    params: dict[str, int | str] = field(default_factory=dict)


def reason_text(r: Reason, locale: str) -> str:
    return t(locale, f"price.{r.key}", **r.params)


@dataclass(frozen=True)
class Suggestion:
    stay_date: date
    kind: str  # raise | hold | lower
    change_pct: int  # +10, 0, −5 …
    confidence: str  # high | medium
    reasons: tuple[Reason, ...]


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _pct(v: Decimal) -> int:
    return int((v * 100).quantize(Decimal(1)))


def suggest(n: NightSignals) -> Suggestion | None:
    if n.own_status != "available" or not n.own_price or not n.comp_median_price:
        return None
    if n.comp_observed < 2:
        return None
    idx = float(n.own_price / n.comp_median_price * 100)
    sold_share = Decimal(n.comp_sold_out) / Decimal(n.comp_observed)

    sold = Reason("comp_sold_out", {"sold": n.comp_sold_out, "observed": n.comp_observed})
    tight: list[Reason] = []
    if sold_share >= SOLD_SHARE_TIGHT:
        tight.append(sold)
    if n.comp_occ is not None and n.comp_occ >= COMP_OCC_TIGHT:
        tight.append(Reason("comp_occ", {"pct": _pct(n.comp_occ)}))
    if n.comp_pace is not None and n.comp_pace >= PACE_FAST:
        tight.append(Reason("comp_pace", {"pts": _pct(n.comp_pace)}))
    extra: list[Reason] = []
    if n.own_rooms_left is not None and n.own_rooms_left <= 3:
        extra.append(Reason("own_rooms_few", {"count": n.own_rooms_left}))
    if n.holiday:
        extra.append(Reason("holiday", {"holiday": n.holiday}))

    if idx < 97 and tight:
        change = min(15, max(5, _round5(100 - idx)))
        return Suggestion(
            n.stay_date,
            "raise",
            change,
            "high" if len(tight) >= 2 else "medium",
            (*tight, Reason("below_median", {"pct": round(100 - idx)}), *extra),
        )
    if idx > 110 and (
        sold_share >= Decimal("0.3")
        or (n.comp_occ is not None and n.comp_occ >= Decimal("0.75"))
        or (n.comp_pace is not None and n.comp_pace >= Decimal("0.1"))
    ):
        reasons = [Reason("above_median", {"pct": round(idx - 100)})]
        if n.comp_sold_out:
            reasons.append(sold)
        if n.comp_occ is not None:
            reasons.append(Reason("comp_occ", {"pct": _pct(n.comp_occ)}))
        if n.comp_pace is not None and n.comp_pace > 0:
            reasons.append(Reason("comp_pace", {"pts": _pct(n.comp_pace)}))
        return Suggestion(n.stay_date, "hold", 0, "medium", tuple(reasons))
    plenty = (n.own_occ is not None and n.own_occ < Decimal("0.6")) or (
        n.own_rooms_left is not None and n.own_rooms_left >= 5
    )
    if (
        n.days_to_arrival <= 7
        and idx > 120
        and n.comp_sold_out == 0
        and (n.comp_pace is None or n.comp_pace <= 0)
        and plenty
    ):
        change = -min(10, max(5, _round5((idx - 100) / 2)))
        reasons = [Reason("above_median", {"pct": round(idx - 100)}), Reason("no_comp_sold_out")]
        if n.own_occ is not None:
            reasons.append(Reason("own_occ", {"pct": _pct(n.own_occ)}))
        elif n.own_rooms_left is not None:
            reasons.append(Reason("own_rooms_left", {"count": n.own_rooms_left}))
        reasons.append(Reason("days_to_arrival", {"count": n.days_to_arrival}))
        return Suggestion(n.stay_date, "lower", change, "medium", tuple(reasons))
    return None
