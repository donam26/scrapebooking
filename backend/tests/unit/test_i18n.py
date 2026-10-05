"""Song ngữ backend: catalog vi/en khớp nhau, đọc Accept-Language, và chữ tiếng Anh ở từng nơi
backend tự sinh (lý do gợi ý giá, lỗi URL, ngày lễ, CSV, email)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from string import Formatter
from zoneinfo import ZoneInfo

import pytest
from starlette.requests import Request

from app import i18n
from app.analytics.compset import CompsetDay
from app.api.deps import get_locale
from app.api.schemas import EventOut
from app.channels.registry import UnsupportedUrl, parse_listing_url
from app.export.csv_tables import events_header, events_rows, filename, overview_header
from app.holidays.data import holidays_between
from app.i18n import LOCALES, catalog, normalize_locale, parse_accept_language, t
from app.market.price_suggest import NightSignals, reason_text, suggest
from app.notify.alert_rules import EventFact, NightMarket, evaluate_alerts
from app.notify.fmt import fmt_money, fmt_night
from app.notify.kinds import effective_rules
from app.notify.render import render_alerts, render_test, render_weekly
from app.notify.weekly import WeekEvent, build_weekly_report


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


def test_catalogs_have_identical_keys_and_placeholders() -> None:
    vi = catalog("vi")
    for locale in LOCALES:
        other = catalog(locale)
        assert other.keys() == vi.keys(), locale
        for key, text in other.items():
            assert text.strip(), (locale, key)
            assert _placeholders(text) == _placeholders(vi[key]), (locale, key)


def test_plural_keys_come_in_pairs() -> None:
    for key in catalog("vi"):
        base, _, form = key.rpartition(".")
        if form in ("one", "other"):
            assert f"{base}.one" in catalog("vi") and f"{base}.other" in catalog("vi"), key


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "vi"),
        ("", "vi"),
        ("en", "en"),
        ("EN-gb", "en"),
        ("vi-VN,vi;q=0.9,en;q=0.8", "vi"),
        ("en-GB,en;q=0.9,vi;q=0.8", "en"),
        ("fr-FR,fr;q=0.9,en;q=0.5", "en"),  # ngôn ngữ đầu không hỗ trợ: lấy cái hỗ trợ kế tiếp
        ("vi;q=0.2,en;q=0.7", "en"),  # theo q, không theo thứ tự
        ("en;q=0,vi", "vi"),  # q=0 nghĩa là không nhận
        ("de, ja", "vi"),
        ("*", "vi"),
        ("en;q=abc", "vi"),
    ],
)
def test_parse_accept_language(header: str | None, expected: str) -> None:
    assert parse_accept_language(header) == expected


def test_get_locale_reads_request_header() -> None:
    def req(value: str | None) -> Request:
        headers = [(b"accept-language", value.encode())] if value is not None else []
        return Request({"type": "http", "headers": headers})

    assert get_locale(req("en")) == "en"
    assert get_locale(req("vi")) == "vi"
    assert get_locale(req(None)) == "vi"


def test_normalize_locale() -> None:
    assert normalize_locale("en_US") == "en"
    assert normalize_locale(" EN ") == "en"
    assert normalize_locale("ko") == "vi"
    assert normalize_locale(None) == "vi"


def test_t_falls_back_to_vi_then_key_and_picks_plural(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = {
        "vi": {
            "a.only_vi": "chỉ tiếng Việt",
            "a.x.one": "{count} phòng",
            "a.x.other": "{count} phòng",
        },
        "en": {"a.x.one": "{count} room", "a.x.other": "{count} rooms"},
    }
    monkeypatch.setattr(i18n, "catalog", lambda locale: fake[locale])
    assert t("en", "a.only_vi") == "chỉ tiếng Việt"
    assert t("en", "a.missing") == "a.missing"
    assert t("en", "a.x", count=1) == "1 room"
    assert t("en", "a.x", count=3) == "3 rooms"
    assert t("fr", "a.x", count=3) == "3 phòng"


def test_price_reasons_in_english() -> None:
    n = NightSignals(
        stay_date=date(2026, 10, 10),
        days_to_arrival=8,
        own_status="available",
        own_price=Decimal("80"),
        own_rooms_left=1,
        own_occ=None,
        comp_observed=4,
        comp_sold_out=2,
        comp_median_price=Decimal("100"),
        comp_occ=None,
        comp_pace=None,
        holiday="National Day",
    )
    s = suggest(n)
    assert s is not None and s.kind == "raise"
    assert [reason_text(r, "en") for r in s.reasons] == [
        "2/4 competitors sold out",
        "your price is 20% below the competitor median",
        "you only have 1 room left on Booking",
        "falls on National Day",
    ]
    assert reason_text(s.reasons[0], "vi") == "2/4 đối thủ đã hết phòng"


def test_url_error_in_english() -> None:
    with pytest.raises(UnsupportedUrl) as exc:
        parse_listing_url("https://www.booking.com/searchresults.html")
    assert exc.value.message("en") == (
        "The Booking link must be the page of a single hotel, "
        "e.g. booking.com/hotel/vn/ten-khach-san.html"
    )
    # str(exc) giữ bản tiếng Việt cho CLI và log
    assert str(exc.value).startswith("Đường dẫn Booking cần là trang của một khách sạn")
    with pytest.raises(UnsupportedUrl) as exc:
        parse_listing_url("ftp://x")
    assert exc.value.message("en") == "This link is not valid; it must start with https://"


def test_holiday_names_in_english() -> None:
    start, end = date(2026, 9, 1), date(2026, 9, 3)
    assert [h.name for h in holidays_between("vn", start, end, "en")] == [
        "National Day",
        "National Day (day off in lieu)",
    ]
    assert [h.name for h in holidays_between("vn", start, end)] == [
        "Quốc khánh",
        "Quốc khánh (nghỉ bù)",
    ]


def test_csv_header_and_labels_in_english() -> None:
    assert overview_header("en")[:4] == ("Channel", "Hotel", "Role", "Night")
    assert overview_header("vi")[0] == "Kênh"
    assert events_header("en")[0] == "Observed at"
    event = EventOut(
        id=1,
        hotel_id=3,
        hotel_name="Rex",
        room_type_id=None,
        room_type_name=None,
        stay_date=date(2026, 10, 10),
        event_type="sold_out",
        from_value="available",
        to_value="sold_out",
        delta=None,
        observed_at=datetime(2026, 10, 1, 1, 0, tzinfo=UTC),
        channel="booking",
        confidence="exact",
        previous_scan_run_id=None,
        scan_run_id=7,
    )
    [row] = events_rows([event], {}, ZoneInfo("Asia/Ho_Chi_Minh"), "en")
    assert row[3:6] == ["Whole hotel", "2026-10-10", "Sold out"]
    assert filename("events", date(2026, 10, 1), "en") == "scrapebooking-events-2026-10-01.csv"
    assert filename("overview", date(2026, 10, 1)) == "scrapebooking-tong-quan-2026-10-01.csv"


def test_email_formatting_and_subjects_in_english() -> None:
    assert fmt_money(Decimal("1250000"), "VND", "en") == "₫1,250,000"
    assert fmt_money(Decimal("1250000"), "VND") == "1.250.000 ₫"
    assert fmt_night(date(2026, 10, 3), "en") == "Sat 03/10"

    today = date(2026, 10, 1)
    events = [
        EventFact(1, 1, "Caravelle", None, date(2026, 10, 3), "sold_out", None, None, None, "VND"),
        EventFact(
            2,
            2,
            "Rex",
            None,
            date(2026, 10, 4),
            "price_down",
            "1500000",
            "1200000",
            Decimal("-20"),
            "VND",
        ),
    ]
    market = {date(2026, 10, 3): NightMarket(2, 3)}
    items = evaluate_alerts(effective_rules({}), events, market, today, "en")
    assert [(i.headline, i.detail) for i in items] == [
        ("Caravelle sold out for Sat 03/10", "2/3 competitors sold out for this night"),
        ("Rex cut prices 20% for Sun 04/10", "lowest price ₫1,500,000 → ₫1,200,000"),
    ]
    email = render_alerts("Rex Hotel", items, "http://x", "en")
    assert email.subject == "Caravelle sold out for Sat 03/10 and 1 other change"
    assert '<html lang="en">' in email.html and "View Sat 03/10" in email.html
    assert "Settings › Notifications for Rex Hotel" in email.text

    report = build_weekly_report(
        date(2026, 10, 5),
        [WeekEvent("Caravelle", "sold_out", False)],
        [
            CompsetDay(
                stay_date=date(2026, 10, 10),
                competitors_observed=4,
                competitors_sold_out=3,
                sold_out_share=Decimal("0.75"),
                min_price=None,
                median_price=None,
                currency="VND",
                own_min_price=None,
                own_status=None,
                own_occupancy_pct=None,
                own_rooms_available=None,
                price_index=None,
                own_rank=None,
                priced_hotels=0,
            )
        ],
        holidays_between("vn", date(2026, 10, 5), date(2026, 10, 18), "en"),
    )
    weekly = render_weekly("Rex", report, "http://x", "en")
    assert weekly.subject == (
        "Weekly report 05/10: 1 upcoming night with over half of competitors sold out"
    )
    assert "Competitors sold out 1 time." in weekly.text
    assert render_test("Rex", "http://x", "en").subject == "Test email from ScrapeBooking"


def test_holiday_kind_and_group_are_stable_across_languages() -> None:
    tet = holidays_between("vn", date(2027, 2, 5), date(2027, 2, 9), "en")
    assert {(h.kind, h.group) for h in tet} == {("tet", "tet")} and len(tet) == 5
    sept = holidays_between("vn", date(2026, 9, 2), date(2026, 9, 3))
    assert [(h.kind, h.group) for h in sept] == [
        ("holiday", "national_day"),
        ("holiday", "national_day"),
    ]
    [xmas] = holidays_between("vn", date(2026, 12, 25), date(2026, 12, 25), "en")
    assert (xmas.kind, xmas.group) == ("travel", "christmas_vn")


def test_insight_language_must_be_supported() -> None:
    from pydantic import ValidationError

    from app.api.schemas import TenantCreate, TenantUpdate

    assert TenantUpdate(insight_language="en").insight_language == "en"
    assert TenantUpdate().insight_language is None
    for bad in ("fr", "english-very-long", ""):
        with pytest.raises(ValidationError, match="insight_language must be one of vi, en"):
            TenantUpdate(insight_language=bad)
    with pytest.raises(ValidationError):
        TenantCreate(name="x", insight_language="fr")


def test_user_prompt_names_language_from_catalog() -> None:
    from app.insight.prompt import user_prompt

    assert user_prompt("en").startswith("language: en (English)\n")
    assert user_prompt("vi").startswith("language: vi (tiếng Việt)\n")
    assert user_prompt("ko").startswith("language: ko\n")
