"""Chọn sự kiện của một lượt quét đáng báo cho tenant, theo luật thông báo (hàm thuần).

Chỉ sự kiện của đối thủ (khách sạn mình đã biết qua PMS), chỉ đêm trong cửa sổ `within_days`
tính từ hôm nay giờ địa phương. Mỗi mục là một câu đọc được theo ngôn ngữ báo cáo của tenant
(catalog `alert.*`), gom vào một email mỗi lượt quét.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.channels.registry import BOOKING, channel_name
from app.i18n import DEFAULT_LOCALE, t
from app.notify.fmt import fmt_int, fmt_money, fmt_night, fmt_pct
from app.notify.kinds import NotificationKind, RuleConfig


@dataclass(frozen=True)
class EventFact:
    event_id: int
    hotel_id: int
    hotel_name: str
    room_type_name: str | None  # None = sự kiện mức khách sạn
    stay_date: date
    event_type: str
    from_value: str | None
    to_value: str | None
    delta: Decimal | None
    currency: str | None = None
    role: str = "competitor"
    # Lý do/ngữ cảnh của sự kiện (lowest_rate_shift: cheapest_gone…; đổi giá: khoá gói).
    reason: str | None = None
    detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class NightMarket:
    sold_out: int
    observed: int
    low: int = 0  # đối thủ còn ≤3 phòng (số chính xác)
    # Chỉ số giá niêm yết của bạn (giá bạn / trung vị đối thủ × 100) và cỡ mẫu của trung vị.
    price_index: Decimal | None = None
    sample: str = "insufficient"
    priced: int = 0


@dataclass(frozen=True)
class AlertItem:
    kind: NotificationKind
    hotel_id: int
    hotel_name: str
    stay_date: date
    event_id: int
    headline: str  # "Caravelle hết phòng đêm T7 03/10"
    detail: str  # "2/4 đối thủ đã hết phòng đêm này"


_KIND_ORDER = {
    NotificationKind.OWN_CLOSED: 0,
    NotificationKind.MARKET_TIGHT: 1,
    NotificationKind.COMPETITOR_SOLD_OUT: 2,
    NotificationKind.COMPETITOR_LOW_STOCK: 3,
    NotificationKind.COMPETITOR_PRICE_DROP: 4,
    NotificationKind.COMPETITOR_PRICE_RISE: 5,
    NotificationKind.COMPETITOR_PROMO: 6,
    NotificationKind.OWN_POSITION_DRIFT: 7,
}
# Sự kiện đối thủ làm thay đổi mức căng của đêm (đêm chỉ được xét "căng" khi lượt này có biến động).
_TIGHTENING = ("sold_out", "low_stock_enter", "rooms_decrease", "lowest_rate_shift")
_OWN_CLOSING = ("sold_out", "restricted")


def _in_window(stay: date, today: date, within_days: int) -> bool:
    return 0 <= (stay - today).days < within_days


def evaluate_alerts(
    rules: dict[NotificationKind, RuleConfig],
    events: list[EventFact],
    market: dict[date, NightMarket],
    today: date,
    locale: str = DEFAULT_LOCALE,
    target_index: Decimal = Decimal(100),
) -> list[AlertItem]:
    """`target_index`: định vị mục tiêu (chỉ số giá niêm yết, 100 = ngang trung vị) của chiến lược
    giá khách sạn (Phase 6); dùng cho cảnh báo lệch định vị."""
    items: list[AlertItem] = []

    def night_of(d: date) -> str:
        return fmt_night(d, locale)

    def money(value: str | None, currency: str | None) -> str:
        return fmt_money(value, currency, locale)

    rule = rules.get(NotificationKind.COMPETITOR_SOLD_OUT)
    if rule and rule.active:
        for e in events:
            if e.event_type != "sold_out" or e.room_type_name is not None or e.role != "competitor":
                continue
            if not _in_window(e.stay_date, today, rule.params["within_days"]):
                continue
            night = market.get(e.stay_date, NightMarket(1, 0))
            if night.sold_out < rule.params["min_sold_out"]:
                continue
            detail = (
                t(locale, "alert.sold_out.market", sold=night.sold_out, observed=night.observed)
                if night.observed
                else t(locale, "alert.sold_out.just_now")
            )
            items.append(
                AlertItem(
                    NotificationKind.COMPETITOR_SOLD_OUT,
                    e.hotel_id,
                    e.hotel_name,
                    e.stay_date,
                    e.event_id,
                    t(
                        locale,
                        "alert.sold_out.headline",
                        hotel=e.hotel_name,
                        night=night_of(e.stay_date),
                    ),
                    detail,
                )
            )

    rule = rules.get(NotificationKind.COMPETITOR_LOW_STOCK)
    if rule and rule.active:
        # Sự kiện sắp hết phòng ở mức loại phòng: gom theo (khách sạn, đêm).
        groups: dict[tuple[int, date], list[EventFact]] = defaultdict(list)
        for e in events:
            if e.event_type != "low_stock_enter" or e.room_type_name is None:
                continue
            if e.role != "competitor":
                continue
            if _in_window(e.stay_date, today, rule.params["within_days"]):
                groups[(e.hotel_id, e.stay_date)].append(e)
        for (_, stay), group in groups.items():
            first = group[0]
            rooms = ", ".join(
                t(
                    locale,
                    "alert.low_stock.rooms_left",
                    room=g.room_type_name,
                    count=int(g.to_value),
                    rooms=fmt_int(int(g.to_value), locale),
                )
                if g.to_value and g.to_value.isdigit()
                else t(locale, "alert.low_stock.almost_gone", room=g.room_type_name)
                for g in sorted(group, key=lambda g: g.room_type_name or "")
            )
            items.append(
                AlertItem(
                    NotificationKind.COMPETITOR_LOW_STOCK,
                    first.hotel_id,
                    first.hotel_name,
                    stay,
                    first.event_id,
                    t(
                        locale,
                        "alert.low_stock.headline",
                        hotel=first.hotel_name,
                        night=night_of(stay),
                    ),
                    rooms,
                )
            )

    rule = rules.get(NotificationKind.COMPETITOR_PRICE_DROP)
    if rule and rule.active:
        for e in events:
            if e.event_type != "price_down" or e.room_type_name is not None or e.delta is None:
                continue
            if e.role != "competitor":
                continue
            if -e.delta < rule.params["min_pct"]:
                continue
            if not _in_window(e.stay_date, today, rule.params["within_days"]):
                continue
            items.append(
                AlertItem(
                    NotificationKind.COMPETITOR_PRICE_DROP,
                    e.hotel_id,
                    e.hotel_name,
                    e.stay_date,
                    e.event_id,
                    t(
                        locale,
                        "alert.price_drop.headline",
                        hotel=e.hotel_name,
                        pct=fmt_pct(e.delta),
                        night=night_of(e.stay_date),
                    ),
                    t(
                        locale,
                        "alert.price_drop.detail",
                        before=money(e.from_value, e.currency),
                        after=money(e.to_value, e.currency),
                    ),
                )
            )

    items += _actionable_alerts(rules, events, market, today, locale, target_index)
    items.sort(key=lambda it: (it.stay_date, _KIND_ORDER[it.kind], it.hotel_name))
    return items


def _actionable_alerts(
    rules: dict[NotificationKind, RuleConfig],
    events: list[EventFact],
    market: dict[date, NightMarket],
    today: date,
    locale: str,
    target_index: Decimal,
) -> list[AlertItem]:
    """Loại cảnh báo của roadmap 3.5: đêm căng, đối thủ tăng giá, đối thủ bật KM sâu, lệch định
    vị, khách sạn của bạn bị đóng/hết trên một kênh."""
    items: list[AlertItem] = []

    def night_of(d: date) -> str:
        return fmt_night(d, locale)

    def money(value: str | None, currency: str | None) -> str:
        return fmt_money(value, currency, locale)

    rule = rules.get(NotificationKind.MARKET_TIGHT)
    if rule and rule.active:
        touched: dict[date, EventFact] = {}
        for e in events:
            if e.role == "competitor" and e.event_type in _TIGHTENING:
                touched.setdefault(e.stay_date, e)
        for stay, first in sorted(touched.items()):
            if not _in_window(stay, today, rule.params["within_days"]):
                continue
            m = market.get(stay)
            if m is None or m.observed < 3:
                continue
            tight = m.sold_out + m.low
            if tight * 100 < rule.params["min_share_pct"] * m.observed:
                continue
            detail = t(locale, "alert.tight.detail", tight=tight, observed=m.observed)
            if m.price_index is not None and m.price_index < 100:
                detail += t(
                    locale, "alert.tight.cheaper", index=fmt_int(int(m.price_index), locale)
                )
            items.append(
                AlertItem(
                    NotificationKind.MARKET_TIGHT,
                    0,
                    "",
                    stay,
                    first.event_id,
                    t(locale, "alert.tight.headline", night=night_of(stay)),
                    detail,
                )
            )

    rule = rules.get(NotificationKind.COMPETITOR_PRICE_RISE)
    if rule and rule.active:
        for e in events:
            if e.event_type != "price_up" or e.room_type_name is not None or e.delta is None:
                continue
            if e.role != "competitor" or e.delta < rule.params["min_pct"]:
                continue
            if not _in_window(e.stay_date, today, rule.params["within_days"]):
                continue
            items.append(
                AlertItem(
                    NotificationKind.COMPETITOR_PRICE_RISE,
                    e.hotel_id,
                    e.hotel_name,
                    e.stay_date,
                    e.event_id,
                    t(
                        locale,
                        "alert.price_rise.headline",
                        hotel=e.hotel_name,
                        pct=fmt_pct(e.delta),
                        night=night_of(e.stay_date),
                    ),
                    t(
                        locale,
                        "alert.price_rise.detail",
                        before=money(e.from_value, e.currency),
                        after=money(e.to_value, e.currency),
                    ),
                )
            )

    rule = rules.get(NotificationKind.COMPETITOR_PROMO)
    if rule and rule.active:
        promos: dict[tuple[int, str], list[EventFact]] = defaultdict(list)
        for e in events:
            if e.event_type != "promo_start" or e.role != "competitor" or e.delta is None:
                continue
            if e.delta < rule.params["min_pct"]:
                continue
            if _in_window(e.stay_date, today, rule.params["within_days"]):
                promos[(e.hotel_id, e.to_value or "")].append(e)
        for (_, label), group in promos.items():
            group.sort(key=lambda g: g.stay_date)
            first = group[0]
            depth = max(g.delta for g in group if g.delta is not None)
            items.append(
                AlertItem(
                    NotificationKind.COMPETITOR_PROMO,
                    first.hotel_id,
                    first.hotel_name,
                    first.stay_date,
                    first.event_id,
                    t(
                        locale,
                        "alert.promo.headline",
                        hotel=first.hotel_name,
                        label=label,
                        pct=fmt_int(int(depth), locale),
                    ),
                    t(
                        locale,
                        "alert.promo.detail",
                        count=len(group),
                        first=night_of(first.stay_date),
                        last=night_of(group[-1].stay_date),
                    ),
                )
            )

    rule = rules.get(NotificationKind.OWN_POSITION_DRIFT)
    if rule and rule.active:
        seen: set[date] = set()
        for e in events:
            if e.event_type not in ("price_up", "price_down") or e.room_type_name is not None:
                continue
            stay = e.stay_date
            if stay in seen or not _in_window(stay, today, rule.params["within_days"]):
                continue
            m = market.get(stay)
            if m is None or m.price_index is None or m.sample == "insufficient":
                continue
            gap = m.price_index - target_index
            if abs(gap) <= rule.params["max_gap_pct"]:
                continue
            seen.add(stay)
            key = "alert.drift.above" if gap > 0 else "alert.drift.below"
            items.append(
                AlertItem(
                    NotificationKind.OWN_POSITION_DRIFT,
                    e.hotel_id if e.role == "self" else 0,
                    e.hotel_name if e.role == "self" else "",
                    stay,
                    e.event_id,
                    t(
                        locale,
                        key,
                        night=night_of(stay),
                        pct=fmt_int(int(abs(gap)), locale),
                    ),
                    t(
                        locale,
                        "alert.drift.detail",
                        index=fmt_int(int(m.price_index), locale),
                        target=fmt_int(int(target_index), locale),
                        priced=m.priced,
                    ),
                )
            )

    rule = rules.get(NotificationKind.OWN_CLOSED)
    if rule and rule.active:
        for e in events:
            if e.role != "self" or e.event_type not in _OWN_CLOSING or e.room_type_name:
                continue
            if not _in_window(e.stay_date, today, rule.params["within_days"]):
                continue
            here = channel_name(BOOKING)
            key = {
                "sold_out": "alert.own_closed.sold_out",
                "restricted": "alert.own_closed.restricted",
            }[e.event_type]
            detail = t(locale, "alert.own_closed.detail")
            items.append(
                AlertItem(
                    NotificationKind.OWN_CLOSED,
                    e.hotel_id,
                    e.hotel_name,
                    e.stay_date,
                    e.event_id,
                    t(locale, key, hotel=e.hotel_name, channel=here, night=night_of(e.stay_date)),
                    detail,
                )
            )
    return items
