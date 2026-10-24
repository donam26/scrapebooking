"""UX Phase 3: cảnh báo lệch giá giữa nhóm, việc cần làm trong bản tin sáng, nhóm đối thủ có cân về
giá không, tự nhận loại tệp PMS."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.analytics.compset import CompsetDay
from app.analytics.compset_balance import compset_balance
from app.api.routers.pms import detect_kind
from app.market.pace_report import NightReport
from app.market.pacing import Pace
from app.market.price_suggest import Reason, Suggestion
from app.notify.alert_rules import EventFact, NightMarket, evaluate_alerts
from app.notify.kinds import NotificationKind as K
from app.notify.kinds import effective_rules
from app.notify.morning import build_morning_actions, main_reason
from app.notify.render import render_insight

TODAY = date(2026, 10, 1)
NIGHT = date(2026, 10, 3)


def price_event(
    event_id: int, before: str, after: str, *, hotel: str = "Caravelle", role: str = "competitor"
) -> EventFact:
    kind = "price_down" if Decimal(after) < Decimal(before) else "price_up"
    return EventFact(
        event_id, event_id, hotel, None, NIGHT, kind, before, after, None, "VND", role=role
    )


def only(*kinds: K, **params: dict[str, int]) -> dict[K, object]:
    stored = {str(k): (k in kinds, params.get(str(k), {})) for k in K}
    return effective_rules(stored)  # type: ignore[return-value]


MARKET = {NIGHT: NightMarket(0, 5, priced=5, sample="ok", median=Decimal(2_000_000))}


def test_below_median_alert_only_when_crossing_threshold() -> None:
    events = [
        price_event(1, "1900000", "1600000"),  # −20% so giá giữa, vừa vượt ngưỡng 15%
        price_event(2, "1500000", "1400000", hotel="Rex"),  # đã dưới ngưỡng từ trước: bỏ
        price_event(3, "2100000", "1900000", hotel="Park"),  # −5%: bỏ
        price_event(4, "1900000", "1500000", hotel="Mine", role="self"),  # khách sạn bạn: bỏ
    ]
    items = evaluate_alerts(only(K.COMPETITOR_BELOW_MEDIAN), events, MARKET, TODAY)
    assert [(i.kind, i.event_id) for i in items] == [(K.COMPETITOR_BELOW_MEDIAN, 1)]
    assert items[0].headline == "Caravelle rẻ hơn giá giữa nhóm đối thủ 20% đêm T7 03/10"
    assert items[0].detail == "Giá mới 1.600.000 ₫, giá giữa 2.000.000 ₫ (5 đối thủ có giá)"


def test_above_median_alert_by_vnd_threshold_and_needs_sample() -> None:
    events = [price_event(1, "2050000", "2350000")]  # +17,5% và +350.000 ₫
    rule = {"competitor_above_median": {"within_days": 14, "min_pct": 50, "min_vnd": 300000}}
    items = evaluate_alerts(only(K.COMPETITOR_ABOVE_MEDIAN, **rule), events, MARKET, TODAY)
    assert [i.kind for i in items] == [K.COMPETITOR_ABOVE_MEDIAN]
    thin = {NIGHT: replace(MARKET[NIGHT], sample="insufficient")}
    assert evaluate_alerts(only(K.COMPETITOR_ABOVE_MEDIAN, **rule), events, thin, TODAY) == []
    # Luật xuống không bắt sự kiện tăng giá.
    assert evaluate_alerts(only(K.COMPETITOR_BELOW_MEDIAN), events, MARKET, TODAY) == []


def night(d: date, sug: Suggestion | None, decision: str | None = None) -> NightReport:
    pace = Pace(None, 0, None)
    return NightReport(
        d, (d - TODAY).days, None, None, None, pace, Decimal(3_000_000), "available", None, "VND",
        5, 0, Decimal(3_200_000), None, 0, None, None, 5, None, 0, pace, sug, decision,
    )  # fmt: skip


def day(d: date, sold: int = 0, low: int = 0, observed: int = 5) -> CompsetDay:
    return CompsetDay(
        d, observed, sold, None, None, Decimal(3_200_000), "VND", Decimal(3_000_000), None,
        None, None, None, None, 6, competitors_low=low, sample="ok",
    )  # fmt: skip


def raise_on(d: date, target: int = 3_400_000) -> Suggestion:
    return Suggestion(
        d,
        "raise",
        13,
        "medium",
        (
            Reason("position", {"median": 3_200_000}, None),
            Reason("comp_tight", {"tight": 3, "observed": 5}, 8),
            Reason("weekday", {"day": "T7"}, 5),
        ),
        Decimal(target),
    )


def test_morning_actions_match_today_list_order_and_cap() -> None:
    nights = [
        night(TODAY + timedelta(days=2), raise_on(TODAY + timedelta(days=2))),
        night(TODAY + timedelta(days=4), raise_on(TODAY + timedelta(days=4)), "applied"),
        night(TODAY + timedelta(days=5), Suggestion(TODAY, "hold", 0, "low", ())),
    ]
    days = [day(TODAY, sold=2)] + [
        day(TODAY + timedelta(days=i), sold=2, low=1) for i in range(1, 14)
    ]
    actions, total = build_morning_actions(nights, days, TODAY, 7)
    # 1 gợi ý chưa ghi + đối thủ hết phòng đêm nay + đêm căng (trừ đêm đã có gợi ý/quyết định).
    assert total == 1 + 1 + 11
    assert len(actions) == 5
    first, second = actions[0], actions[1]
    assert (first.kind, first.headline) == ("raise", "Tăng giá lên 3.400.000 ₫")
    assert first.detail == "3/5 đối thủ đã hết hoặc chỉ còn ≤3 phòng (+8%)"  # lý do chính
    assert first.path == f"/hotels/7/dates/{(TODAY + timedelta(days=2)).isoformat()}"
    assert (second.kind, second.headline) == ("sold_out", "2 đối thủ hết phòng đêm nay")
    assert {a.kind for a in actions[2:]} == {"tight"}


def test_main_reason_prefers_demand_signal() -> None:
    reason = main_reason(raise_on(NIGHT))
    assert reason is not None and reason.key == "comp_tight"


def test_brief_email_lists_actions_with_night_links() -> None:
    actions, total = build_morning_actions(
        [night(TODAY + timedelta(days=2), raise_on(TODAY + timedelta(days=2)))],
        [day(TODAY, sold=1)],
        TODAY,
        7,
    )
    email = render_insight(
        "Rex",
        5,
        TODAY,
        {"summary": "Thị trường căng cuối tuần.", "highlights": []},
        "https://app.x",
        actions=actions,
        more=total - len(actions),
        today=TODAY,
    )
    assert "Việc cần làm" in email.html and "Tăng giá lên 3.400.000 ₫" in email.html
    assert 'href="https://app.x/hotels/7/dates/2026-10-03"' in email.html
    assert "Đêm nay · 1 đối thủ hết phòng đêm nay" in email.html
    assert "https://app.x/hotels/7/dates/2026-10-01" in email.text


def test_compset_balance_flags_pricier_group() -> None:
    days = [
        replace(day(TODAY + timedelta(days=i)), median_price=Decimal(6_300_000)) for i in range(5)
    ]
    b = compset_balance(days)
    assert (b.nights, b.ratio, b.pricier) == (5, Decimal("2.10"), True)
    even = compset_balance([day(TODAY + timedelta(days=i)) for i in range(5)])
    assert even.ratio == Decimal("1.07") and not even.pricier
    assert compset_balance(days[:2]).ratio is None  # chưa đủ 3 đêm


def test_detect_pms_file_kind_from_columns() -> None:
    assert detect_kind(["Ngày", "Phòng đã bán", "Tổng phòng", "Doanh thu"]) == "daily"
    assert detect_kind(["Ngày", "Công suất", "ADR"]) == "daily"
    assert detect_kind(["as_of_date", "stay_date", "rooms_otb"]) == "otb_report"
    assert detect_kind(["Ngày ở", "Phòng đã đặt", "Doanh thu"]) == "otb_report"
    assert detect_kind(["Ngày đặt", "Ngày đến", "Ngày đi", "Số phòng"]) == "bookings"
