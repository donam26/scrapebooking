"""Việc cần làm trong bản tin sáng: cùng danh sách với "Việc cần làm" trên Hôm nay (dashboard
`components/today-actions.tsx`), tối đa 5 việc, mỗi việc mở trang chi tiết đêm của khách sạn bạn.

Thứ tự: gợi ý tăng/giảm giá chưa ghi quyết định (giá mục tiêu VND + lý do chính), đối thủ hết phòng
đêm nay, rồi đêm căng (≥ một nửa đối thủ đọc được đã hết hoặc còn ≤3 phòng). "Giữ giá" không phải
việc cần làm. Hàm thuần trên báo cáo nhịp và compset để dễ kiểm thử.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.analytics.compset import CompsetDay
from app.i18n import DEFAULT_LOCALE, t
from app.market.pace_report import NightReport
from app.market.price_suggest import DEMAND_KEYS, Reason, Suggestion, reason_text
from app.notify.fmt import fmt_money

ACTION_NIGHTS = 14
MAX_ACTIONS = 5
TIGHT_SHARE = Decimal("0.5")  # khớp TIGHT_SHARE của dashboard (lib/market-metrics.ts)
# Câu "vì sao" khi không có điều chỉnh cùng chiều (khớp `mainReason` ở dashboard lib/market.ts).
_WHY_KEYS = ("below_usual", "own_occ_low_pms", "own_occ_low_otb", "above_usual")


@dataclass(frozen=True)
class MorningAction:
    stay_date: date
    kind: str  # raise | lower | sold_out | tight
    headline: str
    detail: str
    path: str  # đường dẫn dashboard: chi tiết đêm của khách sạn bạn


def main_reason(s: Suggestion) -> Reason | None:
    """Lý do chính của gợi ý: điều chỉnh cùng chiều lớn nhất (ưu tiên tín hiệu cầu)."""
    sign = -1 if s.kind == "lower" else 1
    same = [r for r in s.reasons if (r.pct or 0) * sign > 0]
    demand = [r for r in same if r.key in DEMAND_KEYS or r.key.startswith("own_occ_high")]
    pool = demand or same
    if pool:
        return max(pool, key=lambda r: (r.pct or 0) * sign)
    for key in _WHY_KEYS:
        hit = next((r for r in s.reasons if r.key == key), None)
        if hit is not None:
            return hit
    return next(
        (r for r in s.reasons if r.pct is None and not r.key.startswith(("clamp_", "position"))),
        None,
    )


def _tight(day: CompsetDay) -> bool:
    observed = day.competitors_observed
    tight = day.competitors_sold_out + day.competitors_low
    return observed >= 2 and Decimal(tight) >= TIGHT_SHARE * observed


def build_morning_actions(
    nights: Sequence[NightReport],
    days: Sequence[CompsetDay],
    today: date,
    own_hotel_id: int | None,
    locale: str = DEFAULT_LOCALE,
) -> tuple[list[MorningAction], int]:
    """(≤5 việc đầu, tổng số việc) trong 14 đêm từ hôm nay."""
    end = today + timedelta(days=ACTION_NIGHTS - 1)

    def path(d: date) -> str:
        return f"/hotels/{own_hotel_id}/dates/{d.isoformat()}" if own_hotel_id else "/today"

    def tight_detail(day: CompsetDay) -> str:
        return t(
            locale,
            "alert.tight.detail",
            tight=day.competitors_sold_out + day.competitors_low,
            observed=day.competitors_observed,
        )

    out: list[MorningAction] = []
    covered: set[date] = set()
    for n in sorted(nights, key=lambda x: x.stay_date):
        s = n.suggestion
        if s is None or s.kind == "hold" or not today <= n.stay_date <= end:
            continue
        covered.add(n.stay_date)
        if n.decision or s.target_price is None:
            continue
        reason = main_reason(s)
        out.append(
            MorningAction(
                n.stay_date,
                s.kind,
                t(
                    locale,
                    f"email.insight.action.{s.kind}",
                    price=fmt_money(s.target_price, n.currency, locale),
                ),
                reason_text(reason, locale) if reason else "",
                path(n.stay_date),
            )
        )
    by_day = {d.stay_date: d for d in days}
    tonight = by_day.get(today)
    if tonight is not None and tonight.competitors_sold_out > 0 and today not in covered:
        covered.add(today)
        out.append(
            MorningAction(
                today,
                "sold_out",
                t(locale, "email.insight.action.sold_out", count=tonight.competitors_sold_out),
                tight_detail(tonight),
                path(today),
            )
        )
    for d in sorted(by_day):
        day = by_day[d]
        if d in covered or not today <= d <= end or not _tight(day):
            continue
        covered.add(d)
        out.append(
            MorningAction(
                d, "tight", t(locale, "email.insight.action.tight"), tight_detail(day), path(d)
            )
        )
    return out[:MAX_ACTIONS], len(out)
