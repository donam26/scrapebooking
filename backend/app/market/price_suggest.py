"""RMS-lite: gợi ý giá có giải thích (roadmap Phase 6, BC C12/N9) — hàm thuần, không tự đẩy giá.

Cấu trúc theo chuẩn RMS cho khách sạn nhỏ (RoomPriceGenie, Atomize):

1. **Giá tham chiếu** = trung vị đối thủ (giá niêm yết, cùng điều kiện, ≥3 đối thủ) × định vị mục
   tiêu (VD 105 = cao hơn trung vị 5% vì điểm review tốt); chưa đủ mẫu thì giá gốc của chiến lược.
2. **Điều chỉnh cộng dồn, mỗi dòng một lý do có số**: mức căng compset, chỉ báo lấp đầy và nhịp
   của đối thủ, OTB/pace của chính bạn (ưu tiên khi có), thứ trong tuần, lễ/sự kiện, sát ngày đến.
3. **Chặn**: không bao giờ gợi ý giảm cho đêm đang căng hoặc khi bạn sắp kín phòng; mức đổi tối đa
   mỗi ngày; giá sàn/trần; làm tròn.
4. **Gợi ý hạn chế ngoài giá**: số đêm tối thiểu đêm cao điểm, tắt KM/gói không hoàn huỷ khi căng,
   bật KM giờ chót khi chậm.

Lý do trả dạng mã + tham số (`Reason`); chữ dịch ở biên API bằng `reason_text`.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.i18n import t

SOLD_SHARE_TIGHT = Decimal("0.5")
COMP_OCC_TIGHT = Decimal("0.85")
PACE_FAST = Decimal("0.15")
MAX_UP_PCT = Decimal(30)
MAX_DOWN_PCT = Decimal(-20)
HOLD_BAND_PCT = 2  # |đổi| < 2% = giữ giá


@dataclass(frozen=True)
class Strategy:
    """Chiến lược giá của khách sạn (bảng price_strategies); mặc định an toàn khi chưa đặt."""

    base_price: Decimal | None = None
    floor: Decimal | None = None
    ceiling: Decimal | None = None
    target_index: Decimal = Decimal(100)
    round_to: int = 10000
    max_daily_change_pct: int = 15
    weekday_adj: dict[int, int] = field(default_factory=dict)  # 0 = thứ Hai … 6 = Chủ nhật
    holiday_uplift_pct: int = 10
    last_minute_days: int = 3
    last_minute_adj_pct: int = -5
    # "strategy": khách sạn đã đặt chiến lược; "typical": chưa đặt → định vị thường ngày của khách
    # sạn (trung vị chỉ số giá 30 đêm tới), để gợi ý chỉ phản ứng với biến động thị trường chứ không
    # kéo giá về trung vị đối thủ; "default": chưa có gì (định vị 100).
    target_source: str = "default"


@dataclass(frozen=True)
class NightSignals:
    stay_date: date
    days_to_arrival: int
    own_status: str | None  # available | sold_out | restricted | unknown | None
    own_price: Decimal | None
    own_rooms_left: int | None  # số kênh báo chính xác
    own_occ: Decimal | None  # 0..1: OTB/PMS trước, sau đó chỉ báo lấp đầy đủ tin cậy
    comp_observed: int
    comp_sold_out: int
    comp_median_price: Decimal | None
    comp_occ: Decimal | None  # trung vị chỉ báo lấp đầy đối thủ (đủ tin cậy)
    comp_pace: Decimal | None  # nhịp đối thủ so các tuần trước cùng thứ (điểm 0..1)
    holiday: str | None = None  # tên ngày lễ đã theo ngôn ngữ người xem
    # Số đối thủ có giá cùng điều kiện (n): <3 không dùng trung vị, 3 = mẫu nhỏ.
    comp_priced: int = 4
    comp_low: int = 0  # đối thủ còn ≤3 phòng
    # OTB của bạn (Phase 5): phòng hơn/kém đêm cùng thứ 4 tuần trước ở cùng lead; sức chứa.
    own_pace_4w: int | None = None
    own_capacity: int | None = None
    own_occ_source: str | None = None  # otb | pms | estimate
    event_name: str | None = None
    event_uplift_pct: int | None = None  # mức tăng cầu người dùng dự kiến cho sự kiện địa phương
    own_index: Decimal | None = None  # chỉ số giá niêm yết hiện tại


@dataclass(frozen=True)
class Reason:
    key: str  # khoá catalog `price.<key>`
    params: dict[str, int | str] = field(default_factory=dict)
    pct: int | None = None  # đóng góp % vào giá mục tiêu (None = thông tin / chặn)


def reason_text(r: Reason, locale: str) -> str:
    text = t(locale, f"price.{r.key}", **r.params)
    if r.pct:
        text += f" ({'+' if r.pct > 0 else ''}{r.pct}%)"
    return text


@dataclass(frozen=True)
class Suggestion:
    stay_date: date
    kind: str  # raise | hold | lower
    change_pct: int  # +10, 0, −5 … so với giá hiện tại của bạn
    confidence: str  # high | medium | low
    reasons: tuple[Reason, ...]
    target_price: Decimal | None = None
    reference_price: Decimal | None = None
    restrictions: tuple[Reason, ...] = ()
    # floor | ceiling | max_change | no_lower_tight | no_lower_without_demand
    clamped: str | None = None


def _pct(v: Decimal) -> int:
    return int((v * 100).quantize(Decimal(1), ROUND_HALF_UP))


def _round(price: Decimal, step: int) -> Decimal:
    if step <= 0:
        return price.quantize(Decimal(1))
    return (price / step).quantize(Decimal(1), ROUND_HALF_UP) * step


def _money(v: Decimal) -> str:
    return f"{int(v):,}".replace(",", ".")


def _reference(n: NightSignals, st: Strategy) -> tuple[Decimal, list[Reason], bool] | None:
    sample_ok = n.comp_median_price is not None and n.comp_priced >= 3
    if sample_ok:
        assert n.comp_median_price is not None
        reasons = [
            Reason(
                "position_typical" if st.target_source == "typical" else "position",
                {
                    "median": _money(n.comp_median_price),
                    "target": int(st.target_index),
                    "priced": n.comp_priced,
                },
            )
        ]
        if n.comp_priced == 3:
            reasons.append(Reason("small_sample", {"priced": n.comp_priced}))
        return n.comp_median_price * st.target_index / 100, reasons, True
    if st.base_price:
        return st.base_price, [Reason("base_price", {"price": _money(st.base_price)})], False
    return None


def _adjustments(n: NightSignals, st: Strategy) -> tuple[list[Reason], bool, bool, bool]:
    """(các điều chỉnh %, đêm đang căng, bạn sắp kín, thị trường mềm)."""
    adj: list[Reason] = []
    tight_n = n.comp_sold_out + n.comp_low
    share = Decimal(tight_n) / n.comp_observed if n.comp_observed else Decimal(0)
    tight = n.comp_observed >= 3 and share >= SOLD_SHARE_TIGHT
    if n.comp_observed >= 3 and share >= Decimal("0.75"):
        adj.append(Reason("comp_tight", {"tight": tight_n, "observed": n.comp_observed}, 10))
    elif tight:
        adj.append(Reason("comp_tight", {"tight": tight_n, "observed": n.comp_observed}, 5))
    if n.comp_occ is not None and n.comp_occ >= COMP_OCC_TIGHT:
        adj.append(Reason("comp_occ", {"pct": _pct(n.comp_occ)}, 5))
        tight = True
    if n.comp_pace is not None and n.comp_pace >= PACE_FAST:
        adj.append(Reason("comp_pace", {"pts": _pct(n.comp_pace)}, 5))
    # Nửa còn lại của quyết định: OTB/pace của chính bạn.
    own_full = False
    if n.own_occ is not None:
        occ_pct, src = _pct(n.own_occ), n.own_occ_source or "estimate"
        if n.own_occ >= Decimal("0.9"):
            adj.append(Reason(f"own_occ_high_{src}", {"pct": occ_pct}, 10))
            own_full = True
        elif n.own_occ >= Decimal("0.8"):
            adj.append(Reason(f"own_occ_high_{src}", {"pct": occ_pct}, 5))
            own_full = True
    elif n.own_rooms_left is not None and n.own_rooms_left <= 3:
        adj.append(Reason("own_rooms_few", {"count": n.own_rooms_left}, 5))
    if n.own_pace_4w is not None and n.own_capacity:
        pts = Decimal(n.own_pace_4w) / n.own_capacity * 100
        if pts >= 10:
            adj.append(Reason("own_pace_ahead", {"rooms": n.own_pace_4w}, 5))
        elif pts <= -10 and n.days_to_arrival <= 21:
            adj.append(Reason("own_pace_behind", {"rooms": -n.own_pace_4w}, -5))
    wd = st.weekday_adj.get(n.stay_date.weekday())
    if wd:
        adj.append(Reason("weekday", {"day": n.stay_date.weekday()}, wd))
    if n.holiday:
        adj.append(Reason("holiday", {"holiday": n.holiday}, st.holiday_uplift_pct))
    if n.event_name and n.event_uplift_pct:
        up = max(-20, min(20, n.event_uplift_pct // 2))
        adj.append(Reason("event", {"event": n.event_name, "uplift": n.event_uplift_pct}, up))
    soft = not tight and (n.own_occ is None or n.own_occ < Decimal("0.7"))
    if 0 <= n.days_to_arrival <= st.last_minute_days and soft and st.last_minute_adj_pct:
        adj.append(Reason("last_minute", {"count": n.days_to_arrival}, st.last_minute_adj_pct))
    return adj, tight, own_full, soft


def suggest(n: NightSignals, strategy: Strategy | None = None) -> Suggestion | None:
    st = strategy or Strategy()
    if n.own_status != "available" or not n.own_price:
        return None
    base = _reference(n, st)
    if base is None:
        return None
    ref, reasons, sample_ok = base
    adj, tight, own_full, soft = _adjustments(n, st)
    total = max(MAX_DOWN_PCT, min(MAX_UP_PCT, Decimal(sum(r.pct or 0 for r in adj))))
    target = ref * (1 + total / 100)
    reasons += adj

    clamped: str | None = None
    if (tight or own_full) and target < n.own_price:
        # Không bao giờ gợi ý giảm giá cho đêm đang căng / khi bạn sắp kín phòng.
        target, clamped = n.own_price, "no_lower_tight"
        reasons.append(Reason("no_lower_tight"))
    step = Decimal(st.max_daily_change_pct) / 100
    hi, lo = n.own_price * (1 + step), n.own_price * (1 - step)
    if target > hi or target < lo:
        target = min(hi, max(lo, target))
        clamped = "max_change"
        reasons.append(Reason("clamp_max_change", {"pct": st.max_daily_change_pct}))
    if st.floor is not None and target < st.floor:
        target, clamped = st.floor, "floor"
        reasons.append(Reason("clamp_floor", {"price": _money(st.floor)}))
    if st.ceiling is not None and target > st.ceiling:
        target, clamped = st.ceiling, "ceiling"
        reasons.append(Reason("clamp_ceiling", {"price": _money(st.ceiling)}))
    target = _round(target, st.round_to)
    change = int(((target / n.own_price - 1) * 100).quantize(Decimal(1), ROUND_HALF_UP))
    kind = "raise" if change >= HOLD_BAND_PCT else "lower" if change <= -HOLD_BAND_PCT else "hold"
    # Giảm giá cần bằng chứng cầu yếu của chính khách sạn (OTB/PMS hoặc pace), hoặc định vị mục
    # tiêu khách sạn tự đặt; chỉ "lệch định vị" hay "sát ngày" theo ước tính thì giữ giá.
    evidence = n.own_occ_source in ("otb", "pms") or n.own_pace_4w is not None
    if kind == "lower" and not evidence and st.target_source != "strategy":
        target, change, kind, clamped = n.own_price, 0, "hold", "no_lower_without_demand"
        reasons.append(Reason("no_lower_without_demand"))

    restrictions: list[Reason] = []
    peak = n.holiday is not None or n.stay_date.weekday() in (4, 5)
    if peak and tight and n.days_to_arrival >= 7 and (n.own_occ or Decimal(0)) >= Decimal("0.6"):
        restrictions.append(Reason("restrict_min_stay", {"nights": 2}))
    if tight and n.own_index is not None and n.own_index < st.target_index - 3:
        restrictions.append(Reason("restrict_stop_discounts"))
    if (
        n.days_to_arrival <= 7
        and soft
        and n.own_occ is not None
        and n.own_occ < Decimal("0.5")
        and kind != "raise"
    ):
        restrictions.append(Reason("restrict_open_promo"))

    has_otb = n.own_occ_source in ("otb", "pms")
    full_sample = sample_ok and n.comp_priced >= 4
    confidence = "high" if full_sample and has_otb else "medium" if full_sample else "low"
    return Suggestion(
        n.stay_date,
        kind,
        change,
        confidence,
        tuple(reasons),
        target,
        _round(ref, st.round_to),
        tuple(restrictions),
        clamped,
    )


def backtest_verdict(kind: str, actual_occ: Decimal) -> str:
    """Đánh giá hướng gợi ý sau đêm lưu trú: tăng mà vẫn kín (≥85%) là đúng, tăng mà ế (<60%) cần
    xem lại; giảm mà lấp được (≥70%) là đúng, giảm mà vẫn ế (<50%) cần xem lại; giữ không chấm."""
    if kind == "raise":
        if actual_occ >= Decimal("0.85"):
            return "good"
        return "review" if actual_occ < Decimal("0.6") else "neutral"
    if kind == "lower":
        if actual_occ >= Decimal("0.7"):
            return "good"
        return "review" if actual_occ < Decimal("0.5") else "neutral"
    return "neutral"
