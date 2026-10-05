"""Gợi ý giá theo luật cố định (hàm thuần), không tự đẩy giá.

Mỗi gợi ý kèm lý do là số liệu đã quan sát (đối thủ hết phòng, công suất ước tính, nhịp so cùng
kỳ, giá so trung vị), trả dạng mã + tham số (`Reason`); chữ dịch ở biên API bằng `reason_text`.
Ba loại:
- raise: bạn rẻ hơn trung vị trong khi thị trường căng → cân nhắc tăng về gần trung vị.
- hold: bạn đắt hơn trung vị nhưng thị trường đang bán tốt → chưa cần giảm.
- lower: đêm gần (≤ 7 ngày), bạn đắt hơn nhiều, thị trường không căng, bạn còn nhiều phòng.

Giá so sánh cùng loại (`price_basis`): giá hoàn huỷ được khi khách sạn bạn có và ít nhất nửa đối
thủ (có giá, cùng tiền tệ) có; không thì giá thấp nhất mọi loại. Đối thủ có giá nhưng khác tiền tệ
với bạn bị bỏ qua (không trộn tiền tệ). Ngưỡng của luật nằm trong `SuggestionThresholds`, dựng từ
`Settings.suggest_*` để chỉnh không cần sửa code.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from app.i18n import t

if TYPE_CHECKING:
    from app.config import Settings

PriceBasis = Literal["refundable", "any"]


@dataclass(frozen=True)
class SuggestionThresholds:
    """Ngưỡng luật gợi ý giá. Mặc định = giá trị đã dùng từ trước; đổi qua `Settings.suggest_*`."""

    # Chỉ số giá = giá bạn / trung vị đối thủ × 100.
    index_raise_below: float = 97.0  # rẻ hơn trung vị → cân nhắc tăng (khi thị trường căng)
    index_hold_above: float = 110.0  # đắt hơn trung vị → giữ nếu thị trường vẫn bán tốt
    index_lower_above: float = 120.0  # đắt hơn nhiều → giảm nếu đêm gần và bạn còn nhiều phòng
    # Thị trường "căng" (raise) và "bán tốt" (hold).
    sold_share_tight: Decimal = Decimal("0.5")
    sold_share_hold: Decimal = Decimal("0.3")
    comp_occ_tight: Decimal = Decimal("0.85")
    comp_occ_hold: Decimal = Decimal("0.75")
    pace_fast: Decimal = Decimal("0.15")
    pace_hold: Decimal = Decimal("0.1")
    own_occ_plenty: Decimal = Decimal("0.6")  # dưới mức này = bạn còn nhiều phòng (lower)
    # Mức thay đổi gợi ý (%), làm tròn bội số 5.
    change_min_pct: int = 5
    change_max_raise_pct: int = 15
    change_max_lower_pct: int = 10


def thresholds_from_settings(settings: "Settings") -> SuggestionThresholds:
    return SuggestionThresholds(
        index_raise_below=settings.suggest_index_raise_below,
        index_hold_above=settings.suggest_index_hold_above,
        index_lower_above=settings.suggest_index_lower_above,
        sold_share_tight=Decimal(str(settings.suggest_sold_share_tight)),
        sold_share_hold=Decimal(str(settings.suggest_sold_share_hold)),
        comp_occ_tight=Decimal(str(settings.suggest_comp_occ_tight)),
        comp_occ_hold=Decimal(str(settings.suggest_comp_occ_hold)),
        pace_fast=Decimal(str(settings.suggest_pace_fast)),
        pace_hold=Decimal(str(settings.suggest_pace_hold)),
        own_occ_plenty=Decimal(str(settings.suggest_own_occ_plenty)),
        change_min_pct=settings.suggest_change_min_pct,
        change_max_raise_pct=settings.suggest_change_max_raise_pct,
        change_max_lower_pct=settings.suggest_change_max_lower_pct,
    )


DEFAULT_THRESHOLDS = SuggestionThresholds()


@dataclass(frozen=True)
class PriceQuote:
    """Giá một khách sạn một đêm (từ `hotel_date_metrics`): thấp nhất mọi loại và hoàn huỷ được."""

    currency: str | None
    min_price: Decimal | None
    min_refundable_price: Decimal | None


@dataclass(frozen=True)
class PricePick:
    basis: PriceBasis
    own_price: Decimal | None
    comp_prices: tuple[Decimal, ...]


def comparable(own_currency: str | None, comp: PriceQuote) -> bool:
    """Đối thủ dùng được để so với bạn: không có giá (hết phòng) hoặc cùng tiền tệ. Khi bạn chưa có
    tiền tệ (không có giá) thì không lọc."""
    return comp.min_price is None or own_currency is None or comp.currency == own_currency


def price_basis(own: PriceQuote | None, comps: Sequence[PriceQuote]) -> PricePick:
    """Chọn cơ sở giá so sánh cho các đối thủ đã qua `comparable`: hoàn huỷ khi bạn có và ≥ nửa
    đối thủ có giá cũng có; không thì giá thấp nhất mọi loại."""
    priced = [c for c in comps if c.min_price is not None]
    refundable = [c.min_refundable_price for c in priced if c.min_refundable_price is not None]
    if own is not None and own.min_refundable_price is not None and priced:
        if 2 * len(refundable) >= len(priced):
            return PricePick("refundable", own.min_refundable_price, tuple(refundable))
    return PricePick(
        "any",
        own.min_price if own else None,
        tuple(c.min_price for c in priced if c.min_price is not None),
    )


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
    price_basis: PriceBasis = "any"  # cơ sở của own_price và comp_median_price


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
    price_basis: PriceBasis = "any"


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _pct(v: Decimal) -> int:
    return int((v * 100).quantize(Decimal(1)))


def suggest(n: NightSignals, th: SuggestionThresholds = DEFAULT_THRESHOLDS) -> Suggestion | None:
    if n.own_status != "available" or not n.own_price or not n.comp_median_price:
        return None
    if n.comp_observed < 2:
        return None
    idx = float(n.own_price / n.comp_median_price * 100)
    sold_share = Decimal(n.comp_sold_out) / Decimal(n.comp_observed)

    sold = Reason("comp_sold_out", {"sold": n.comp_sold_out, "observed": n.comp_observed})
    tight: list[Reason] = []
    if sold_share >= th.sold_share_tight:
        tight.append(sold)
    if n.comp_occ is not None and n.comp_occ >= th.comp_occ_tight:
        tight.append(Reason("comp_occ", {"pct": _pct(n.comp_occ)}))
    if n.comp_pace is not None and n.comp_pace >= th.pace_fast:
        tight.append(Reason("comp_pace", {"pts": _pct(n.comp_pace)}))
    extra: list[Reason] = []
    if n.own_rooms_left is not None and n.own_rooms_left <= 3:
        extra.append(Reason("own_rooms_few", {"count": n.own_rooms_left}))
    if n.holiday:
        extra.append(Reason("holiday", {"holiday": n.holiday}))

    if idx < th.index_raise_below and tight:
        change = min(th.change_max_raise_pct, max(th.change_min_pct, _round5(100 - idx)))
        return Suggestion(
            n.stay_date,
            "raise",
            change,
            "high" if len(tight) >= 2 else "medium",
            (*tight, Reason("below_median", {"pct": round(100 - idx)}), *extra),
            n.price_basis,
        )
    if idx > th.index_hold_above and (
        sold_share >= th.sold_share_hold
        or (n.comp_occ is not None and n.comp_occ >= th.comp_occ_hold)
        or (n.comp_pace is not None and n.comp_pace >= th.pace_hold)
    ):
        reasons = [Reason("above_median", {"pct": round(idx - 100)})]
        if n.comp_sold_out:
            reasons.append(sold)
        if n.comp_occ is not None:
            reasons.append(Reason("comp_occ", {"pct": _pct(n.comp_occ)}))
        if n.comp_pace is not None and n.comp_pace > 0:
            reasons.append(Reason("comp_pace", {"pts": _pct(n.comp_pace)}))
        return Suggestion(n.stay_date, "hold", 0, "medium", tuple(reasons), n.price_basis)
    plenty = (n.own_occ is not None and n.own_occ < th.own_occ_plenty) or (
        n.own_rooms_left is not None and n.own_rooms_left >= 5
    )
    if (
        n.days_to_arrival <= 7
        and idx > th.index_lower_above
        and n.comp_sold_out == 0
        and (n.comp_pace is None or n.comp_pace <= 0)
        and plenty
    ):
        change = -min(th.change_max_lower_pct, max(th.change_min_pct, _round5((idx - 100) / 2)))
        reasons = [Reason("above_median", {"pct": round(idx - 100)}), Reason("no_comp_sold_out")]
        if n.own_occ is not None:
            reasons.append(Reason("own_occ", {"pct": _pct(n.own_occ)}))
        elif n.own_rooms_left is not None:
            reasons.append(Reason("own_rooms_left", {"count": n.own_rooms_left}))
        reasons.append(Reason("days_to_arrival", {"count": n.days_to_arrival}))
        return Suggestion(n.stay_date, "lower", change, "medium", tuple(reasons), n.price_basis)
    return None
