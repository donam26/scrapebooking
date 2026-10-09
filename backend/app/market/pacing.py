"""Nhịp (so các tuần trước, cùng thứ — không phải STLY) và đối chiếu với PMS (hàm thuần).

Nhịp của một đêm ở số ngày trước khi đến d = công suất hiện tại − trung vị công suất của các đêm
tham chiếu ở cùng d: cùng thứ trong tuần, 1–8 tuần trước, cùng là ngày lễ hoặc cùng không. Cần ít
nhất MIN_REFERENCES đêm tham chiếu; thiếu thì nói thẳng "chưa đủ lịch sử".
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.analytics.rules import median

REFERENCE_WEEKS = range(1, 9)
MIN_REFERENCES = 2
LEAD_TOLERANCE = 1  # chấp nhận quan sát lệch 1 ngày so với d (lịch quét không trùng giờ)


@dataclass(frozen=True)
class Pace:
    reference: Decimal | None  # trung vị công suất các đêm tham chiếu ở cùng d
    references: int  # số đêm tham chiếu dùng được
    delta: Decimal | None  # hiện tại − tham chiếu (âm = chậm hơn các tuần trước)


def occ_at_lead(curve: dict[int, Decimal], lead: int) -> Decimal | None:
    """Công suất của một đêm ở d ngày trước khi đến, lấy quan sát gần d nhất trong dung sai."""
    for off in range(LEAD_TOLERANCE + 1):
        for d in (lead + off, lead - off) if off else (lead,):
            if d in curve:
                return curve[d]
    return None


def pace(
    night: date,
    lead: int,
    occ_now: Decimal | None,
    curves: dict[date, dict[int, Decimal]],
    is_holiday: Callable[[date], bool],
) -> Pace:
    """`curves[đêm][d]` = công suất của đêm đó khi còn d ngày (chỉ quan sát đủ tin cậy)."""
    holiday = is_holiday(night)
    refs = []
    for w in REFERENCE_WEEKS:
        m = night - timedelta(weeks=w)
        if is_holiday(m) != holiday or m not in curves:
            continue
        v = occ_at_lead(curves[m], lead)
        if v is not None:
            refs.append(v)
    if len(refs) < MIN_REFERENCES:
        return Pace(None, len(refs), None)
    ref = median(refs)
    assert ref is not None
    return Pace(
        ref, len(refs), (occ_now - ref).quantize(Decimal("0.0001")) if occ_now is not None else None
    )


def compset_curve(
    per_hotel: Iterable[dict[int, Decimal]], min_hotels: int = 2
) -> dict[int, Decimal]:
    """Đường công suất của thị trường: trung vị các đối thủ ở mỗi d, khi đủ `min_hotels` đối thủ."""
    by_lead: dict[int, list[Decimal]] = {}
    for curve in per_hotel:
        for d, v in curve.items():
            by_lead.setdefault(d, []).append(v)
    out: dict[int, Decimal] = {}
    for d, values in by_lead.items():
        if len(values) >= min_hotels:
            m = median(values)
            if m is not None:
                out[d] = m
    return out


@dataclass(frozen=True)
class Calibration:
    nights: int
    mean_abs_error_pts: Decimal | None  # điểm phần trăm
    bias_pts: Decimal | None  # ước tính − PMS, dương = ước tính cao hơn thực tế


def calibrate(pairs: Iterable[tuple[Decimal, Decimal]]) -> Calibration:
    """(công suất ước tính 0..1, công suất PMS 0..1) của các đêm đã qua, cùng khách sạn."""
    diffs = [(est - real) * 100 for est, real in pairs]
    if not diffs:
        return Calibration(0, None, None)
    n = Decimal(len(diffs))
    mae = (sum(abs(d) for d in diffs) / n).quantize(Decimal("0.1"))
    bias = (sum(diffs) / n).quantize(Decimal("0.1"))
    return Calibration(len(diffs), mae, bias)


# Nhóm số ngày trước khi đến để báo sai số chỉ báo lấp đầy so với PMS (roadmap 1.3, 5.6).
LEAD_BUCKETS: tuple[tuple[str, int, int], ...] = (("0-7", 0, 7), ("8-30", 8, 30), ("31-90", 31, 90))
# Sai số tuyệt đối trung bình (điểm %) quá ngưỡng này thì giao diện ẩn chỉ báo ở nhóm đó.
MAX_USABLE_MAE_PTS = Decimal(20)


@dataclass(frozen=True)
class LeadCalibration:
    bucket: str
    nights: int
    mean_abs_error_pts: Decimal | None
    bias_pts: Decimal | None
    # MAPE (%) so với công suất PMS > 0; None khi không có đêm nào có công suất PMS > 0.
    mape_pct: Decimal | None
    usable: bool


def calibrate_by_lead(
    triples: Iterable[tuple[int, Decimal, Decimal]],
) -> list[LeadCalibration]:
    """(số ngày trước khi đến lúc ước tính, ước tính 0..1, PMS cuối cùng 0..1) → sai số theo nhóm
    lead time. Chỉ báo từ tồn phòng OTA không có chuẩn tuyệt đối (Suzuki 2023): phải tự hiệu
    chỉnh bằng chính khách sạn của bạn."""
    rows = list(triples)
    out = []
    for name, lo, hi in LEAD_BUCKETS:
        sel = [(est, real) for lead, est, real in rows if lo <= lead <= hi]
        cal = calibrate(sel)
        nonzero = [(est, real) for est, real in sel if real > 0]
        mape = (
            (
                Decimal(sum((abs(est - real) / real for est, real in nonzero), Decimal(0)))
                / len(nonzero)
                * 100
            ).quantize(Decimal("0.1"))
            if nonzero
            else None
        )
        out.append(
            LeadCalibration(
                name,
                cal.nights,
                cal.mean_abs_error_pts,
                cal.bias_pts,
                mape,
                cal.mean_abs_error_pts is not None and cal.mean_abs_error_pts <= MAX_USABLE_MAE_PTS,
            )
        )
    return out
