"""Loại thông báo, tham số mặc định và miền giá trị hợp lệ.

Mỗi tenant có tối đa một dòng `notification_rules` mỗi loại; chưa có dòng thì loại đó bật với
tham số mặc định, để khách sạn nhận cảnh báo ngay khi đã thêm người nhận.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class NotificationKind(StrEnum):
    DAILY_INSIGHT = "daily_insight"
    WEEKLY_REPORT = "weekly_report"
    COMPETITOR_SOLD_OUT = "competitor_sold_out"
    COMPETITOR_LOW_STOCK = "competitor_low_stock"
    COMPETITOR_PRICE_DROP = "competitor_price_drop"
    # Roadmap 3.5: cảnh báo hành động được.
    MARKET_TIGHT = "market_tight"  # đêm căng: ≥x% đối thủ hết/sắp hết (cơ hội tăng giá)
    COMPETITOR_PRICE_RISE = "competitor_price_rise"  # đối thủ TĂNG giá cùng phòng + gói
    COMPETITOR_PROMO = "competitor_promo"  # đối thủ bật KM sâu ≥x% (radar KM, 4.1)
    OWN_POSITION_DRIFT = "own_position_drift"  # giá bạn lệch định vị mục tiêu > x%
    OWN_CLOSED = "own_closed"  # bạn hết phòng / không nhận khách ngày đến trên Booking.com
    DATA_STALE = "data_stale"  # dữ liệu cũ hơn một chu kỳ quét


# Loại sinh từ sự kiện của một lượt quét, gom chung vào một email cảnh báo mỗi lượt.
ALERT_KINDS = (
    NotificationKind.COMPETITOR_SOLD_OUT,
    NotificationKind.COMPETITOR_LOW_STOCK,
    NotificationKind.COMPETITOR_PRICE_DROP,
    NotificationKind.MARKET_TIGHT,
    NotificationKind.COMPETITOR_PRICE_RISE,
    NotificationKind.COMPETITOR_PROMO,
    NotificationKind.OWN_POSITION_DRIFT,
    NotificationKind.OWN_CLOSED,
)

DEFAULT_PARAMS: dict[NotificationKind, dict[str, int]] = {
    NotificationKind.DAILY_INSIGHT: {},
    NotificationKind.WEEKLY_REPORT: {},
    NotificationKind.COMPETITOR_SOLD_OUT: {"within_days": 14, "min_sold_out": 1},
    NotificationKind.COMPETITOR_LOW_STOCK: {"within_days": 7},
    NotificationKind.COMPETITOR_PRICE_DROP: {"within_days": 14, "min_pct": 10},
    NotificationKind.MARKET_TIGHT: {"within_days": 14, "min_share_pct": 50},
    NotificationKind.COMPETITOR_PRICE_RISE: {"within_days": 14, "min_pct": 10},
    NotificationKind.COMPETITOR_PROMO: {"within_days": 30, "min_pct": 20},
    NotificationKind.OWN_POSITION_DRIFT: {"within_days": 14, "max_gap_pct": 10},
    NotificationKind.OWN_CLOSED: {"within_days": 30},
    NotificationKind.DATA_STALE: {},
}

# Loại mặc định tắt (bật trong Cài đặt): lệch định vị cần khách sạn đặt mục tiêu trước.
DEFAULT_OFF = frozenset({NotificationKind.OWN_POSITION_DRIFT})

PARAM_BOUNDS: dict[str, tuple[int, int]] = {
    "within_days": (1, 90),
    "min_sold_out": (1, 50),
    "min_pct": (3, 90),
    "min_share_pct": (25, 100),
    "max_gap_pct": (3, 50),
}


@dataclass(frozen=True)
class RuleConfig:
    kind: NotificationKind
    active: bool
    params: dict[str, int]


class InvalidParams(ValueError):
    pass


def normalize_params(kind: NotificationKind, raw: dict[str, Any] | None) -> dict[str, int]:
    """Gộp với mặc định và kiểm tra: chỉ khoá của loại đó, số nguyên trong miền cho phép."""
    defaults = DEFAULT_PARAMS[kind]
    raw = raw or {}
    unknown = set(raw) - set(defaults)
    if unknown:
        raise InvalidParams(f"unknown params for {kind}: {', '.join(sorted(unknown))}")
    out = dict(defaults)
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidParams(f"{key} must be an integer")
        lo, hi = PARAM_BOUNDS[key]
        if not lo <= value <= hi:
            raise InvalidParams(f"{key} must be between {lo} and {hi}")
        out[key] = value
    return out


def effective_rules(
    stored: dict[str, tuple[bool, dict[str, Any]]],
) -> dict[NotificationKind, RuleConfig]:
    """Luật đang áp dụng của tenant: dòng đã lưu, hoặc mặc định (bật) cho loại chưa có dòng.
    Tham số đã lưu sai miền (dữ liệu cũ) thì quay về mặc định thay vì làm hỏng cả lượt gửi."""
    out: dict[NotificationKind, RuleConfig] = {}
    for kind in NotificationKind:
        active, params = stored.get(str(kind), (kind not in DEFAULT_OFF, {}))
        try:
            norm = normalize_params(kind, params)
        except InvalidParams:
            norm = dict(DEFAULT_PARAMS[kind])
        out[kind] = RuleConfig(kind, active, norm)
    return out
