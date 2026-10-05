"""Bảng ngày lễ tĩnh theo nước (spec mục 4: holidays/). Bổ sung khi onboard tenant nước mới.

Ngày âm lịch (Tết, Giỗ Tổ) ghi theo dương lịch của từng năm.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.i18n import DEFAULT_LOCALE, t

# tet: Tết/năm mới âm lịch; travel: không phải ngày nghỉ nhưng cầu du lịch cao; holiday: còn lại.
HolidayKind = Literal["tet", "holiday", "travel"]


@dataclass(frozen=True)
class Holiday:
    date: date
    name: str  # theo ngôn ngữ người xem
    country: str
    kind: HolidayKind = "holiday"
    # Mã đợt nghỉ, ổn định giữa các ngôn ngữ: các ngày cùng đợt (Tết mùng 1–4, Quốc khánh + nghỉ
    # bù) cùng một `group` để giao diện gộp thành một khoảng.
    group: str = ""


# Mã ngày lễ -> mã đợt (mặc định chính mã đó) và loại (theo đợt, mặc định "holiday").
_GROUP = {
    "tet_eve": "tet",
    "tet_1": "tet",
    "tet_2": "tet",
    "tet_3": "tet",
    "tet_4": "tet",
    "national_day_in_lieu": "national_day",
    "boxing_day_in_lieu": "boxing_day",
}
_KIND: dict[str, HolidayKind] = {
    "tet": "tet",
    "chinese_new_year": "tet",
    "christmas_vn": "travel",
}


# (ngày, mã tên); tên đọc từ catalog `holiday.<mã>` theo ngôn ngữ.
_HOLIDAYS: dict[str, list[tuple[str, str]]] = {
    "vn": [
        ("2026-01-01", "new_year"),
        ("2026-02-16", "tet_eve"),
        ("2026-02-17", "tet_1"),
        ("2026-02-18", "tet_2"),
        ("2026-02-19", "tet_3"),
        ("2026-02-20", "tet_4"),
        ("2026-04-26", "hung_kings"),
        ("2026-04-30", "reunification"),
        ("2026-05-01", "labour_day"),
        ("2026-09-02", "national_day"),
        ("2026-09-03", "national_day_in_lieu"),
        ("2026-12-25", "christmas_vn"),
        ("2027-01-01", "new_year"),
        ("2027-02-05", "tet_eve"),
        ("2027-02-06", "tet_1"),
        ("2027-02-07", "tet_2"),
        ("2027-02-08", "tet_3"),
        ("2027-02-09", "tet_4"),
        ("2027-04-16", "hung_kings"),
        ("2027-04-30", "reunification"),
        ("2027-05-01", "labour_day"),
        ("2027-09-02", "national_day"),
    ],
    "th": [
        ("2026-01-01", "new_year"),
        ("2026-04-06", "chakri_day"),
        ("2026-04-13", "songkran"),
        ("2026-04-14", "songkran"),
        ("2026-04-15", "songkran"),
        ("2026-05-01", "labour_day"),
        ("2026-07-28", "king_birthday"),
        ("2026-08-12", "queen_mother_birthday"),
        ("2026-10-13", "king_bhumibol_memorial"),
        ("2026-10-23", "chulalongkorn_day"),
        ("2026-12-05", "king_bhumibol_birthday"),
        ("2026-12-10", "constitution_day"),
        ("2026-12-31", "new_years_eve"),
        ("2027-01-01", "new_year"),
    ],
    "sg": [
        ("2026-01-01", "new_year"),
        ("2026-02-17", "chinese_new_year"),
        ("2026-02-18", "chinese_new_year"),
        ("2026-04-03", "good_friday"),
        ("2026-05-01", "labour_day"),
        ("2026-08-09", "national_day"),
        ("2026-12-25", "christmas_day"),
        ("2027-01-01", "new_year"),
    ],
    "us": [
        ("2026-01-01", "new_year"),
        ("2026-05-25", "memorial_day"),
        ("2026-07-04", "independence_day"),
        ("2026-09-07", "labor_day_us"),
        ("2026-11-26", "thanksgiving"),
        ("2026-12-25", "christmas_day"),
        ("2027-01-01", "new_year"),
    ],
    "gb": [
        ("2026-01-01", "new_year"),
        ("2026-04-03", "good_friday"),
        ("2026-04-06", "easter_monday"),
        ("2026-05-04", "early_may_bank_holiday"),
        ("2026-05-25", "spring_bank_holiday"),
        ("2026-08-31", "summer_bank_holiday"),
        ("2026-12-25", "christmas_day"),
        ("2026-12-28", "boxing_day_in_lieu"),
        ("2027-01-01", "new_year"),
    ],
}


def holidays_between(
    country: str, start: date, end: date, locale: str = DEFAULT_LOCALE
) -> list[Holiday]:
    out = []
    for iso, code in _HOLIDAYS.get(country.lower(), []):
        d = date.fromisoformat(iso)
        if start <= d <= end:
            group = _GROUP.get(code, code)
            out.append(
                Holiday(
                    d,
                    t(locale, f"holiday.{code}"),
                    country.lower(),
                    _KIND.get(group, "holiday"),
                    group,
                )
            )
    return sorted(out, key=lambda h: h.date)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def days_to_next_holiday(country: str, d: date, horizon: int = 60) -> int | None:
    for h in holidays_between(country, d, d + timedelta(days=horizon)):
        return (h.date - d).days
    return None
