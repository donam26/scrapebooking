"""Chọn sự kiện của một lượt quét đáng báo cho tenant, theo luật thông báo (hàm thuần).

Chỉ sự kiện của đối thủ (khách sạn mình đã biết qua PMS), chỉ đêm trong cửa sổ `within_days`
tính từ hôm nay giờ địa phương. Mỗi mục là một câu đọc được theo ngôn ngữ báo cáo của tenant
(catalog `alert.*`), gom vào một email mỗi lượt quét.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.channels.registry import channel_name
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
    # Đa kênh: các kênh có cùng sự kiện ở mốc quét này (gộp một dòng), và với hết phòng: các kênh
    # vẫn bán (sự kiện channel_closed) → nhiều khả năng chỉ đóng kênh, không phải hết phòng thật.
    channels: tuple[str, ...] = ()
    open_elsewhere: tuple[str, ...] = ()
    role: str = "competitor"


def _channels_text(channels: tuple[str, ...]) -> str:
    return ", ".join(channel_name(c) for c in channels)


@dataclass(frozen=True)
class NightMarket:
    sold_out: int
    observed: int


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
    NotificationKind.COMPETITOR_SOLD_OUT: 0,
    NotificationKind.COMPETITOR_LOW_STOCK: 1,
    NotificationKind.COMPETITOR_PRICE_DROP: 2,
    NotificationKind.OWN_PARITY_GAP: 3,
}


def _in_window(stay: date, today: date, within_days: int) -> bool:
    return 0 <= (stay - today).days < within_days


def evaluate_alerts(
    rules: dict[NotificationKind, RuleConfig],
    events: list[EventFact],
    market: dict[date, NightMarket],
    today: date,
    locale: str = DEFAULT_LOCALE,
) -> list[AlertItem]:
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
            if e.open_elsewhere:
                # D4: hết trên kênh này nhưng kênh khác vẫn bán: nói đúng là đóng kênh.
                items.append(
                    AlertItem(
                        NotificationKind.COMPETITOR_SOLD_OUT,
                        e.hotel_id,
                        e.hotel_name,
                        e.stay_date,
                        e.event_id,
                        t(
                            locale,
                            "alert.closed.headline",
                            hotel=e.hotel_name,
                            channels=_channels_text(e.channels),
                            night=night_of(e.stay_date),
                        ),
                        t(
                            locale,
                            "alert.closed.detail",
                            channels=_channels_text(e.open_elsewhere),
                        ),
                    )
                )
                continue
            night = market.get(e.stay_date, NightMarket(1, 0))
            if night.sold_out < rule.params["min_sold_out"]:
                continue
            detail = (
                t(locale, "alert.sold_out.market", sold=night.sold_out, observed=night.observed)
                if night.observed
                else t(locale, "alert.sold_out.just_now")
            )
            if e.channels:
                detail += t(locale, "alert.on_channels", channels=_channels_text(e.channels))
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
                    )
                    + (
                        t(locale, "alert.on_channels", channels=_channels_text(e.channels))
                        if e.channels
                        else ""
                    ),
                )
            )

    rule = rules.get(NotificationKind.OWN_PARITY_GAP)
    if rule and rule.active:
        # Gộp theo (khách sạn, kênh rẻ hơn): một nguồn bán lại thường lệch giá nhiều đêm liền
        # (VD đại lý trên Mytour giá cố định) — một dòng "ở N đêm" thay vì N dòng giống nhau.
        parity: dict[tuple[int, tuple[str, ...]], list[EventFact]] = defaultdict(list)
        for e in events:
            if e.event_type != "parity_gap" or e.role != "self" or e.delta is None:
                continue
            if -e.delta < rule.params["min_pct"]:
                continue
            if not _in_window(e.stay_date, today, rule.params["within_days"]):
                continue
            parity[(e.hotel_id, e.channels)].append(e)
        for (_, channels), group in parity.items():
            group.sort(key=lambda g: g.stay_date)
            first = group[0]
            here = _channels_text(channels) or t(locale, "alert.parity.a_channel")
            gaps = sorted(-g.delta for g in group if g.delta is not None)
            other, _, other_price = (first.from_value or "").partition(":")
            if len(group) == 1:
                headline = t(
                    locale,
                    "alert.parity.headline",
                    hotel=first.hotel_name,
                    pct=fmt_pct(gaps[0]),
                    channel=here,
                    night=night_of(first.stay_date),
                )
                detail = t(
                    locale,
                    "alert.parity.detail",
                    channel=here,
                    price=money(first.to_value, first.currency),
                    other=channel_name(other),
                    other_price=money(other_price, first.currency),
                )
            else:
                pct = (
                    fmt_pct(gaps[0])
                    if gaps[0] == gaps[-1]
                    else f"{fmt_pct(gaps[0])}–{fmt_pct(gaps[-1])}"
                )
                headline = t(
                    locale,
                    "alert.parity.headline_nights",
                    hotel=first.hotel_name,
                    pct=pct,
                    channel=here,
                    count=len(group),
                )
                detail = t(
                    locale,
                    "alert.parity.detail_nights",
                    first=night_of(first.stay_date),
                    last=night_of(group[-1].stay_date),
                    channel=here,
                    price=money(first.to_value, first.currency),
                    other=channel_name(other),
                    other_price=money(other_price, first.currency),
                )
            items.append(
                AlertItem(
                    NotificationKind.OWN_PARITY_GAP,
                    first.hotel_id,
                    first.hotel_name,
                    first.stay_date,
                    first.event_id,
                    headline,
                    detail,
                )
            )

    items.sort(key=lambda it: (it.stay_date, _KIND_ORDER[it.kind], it.hotel_name))
    return items
