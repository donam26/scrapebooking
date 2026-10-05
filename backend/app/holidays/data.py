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
        ("2027-12-25", "christmas_vn"),
        # 2028: Tết Mậu Thân, mùng 1 = 26/01/2028. Giỗ Tổ (10/3 âm lịch) 2028–2029 chưa đối chiếu
        # lịch âm chính thức: bổ sung khi có công bố (ước ~04/04/2028, ~23/04/2029).
        ("2028-01-01", "new_year"),
        ("2028-01-25", "tet_eve"),
        ("2028-01-26", "tet_1"),
        ("2028-01-27", "tet_2"),
        ("2028-01-28", "tet_3"),
        ("2028-01-29", "tet_4"),
        ("2028-04-30", "reunification"),
        ("2028-05-01", "labour_day"),
        ("2028-09-02", "national_day"),
        ("2028-12-25", "christmas_vn"),
        # 2029: Tết Kỷ Dậu, mùng 1 = 13/02/2029.
        ("2029-01-01", "new_year"),
        ("2029-02-12", "tet_eve"),
        ("2029-02-13", "tet_1"),
        ("2029-02-14", "tet_2"),
        ("2029-02-15", "tet_3"),
        ("2029-02-16", "tet_4"),
        ("2029-04-30", "reunification"),
        ("2029-05-01", "labour_day"),
        ("2029-09-02", "national_day"),
        ("2029-12-25", "christmas_vn"),
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
        # 2027–2029: ngày cố định theo luật Thái Lan (ngày bù khi trùng cuối tuần không ghi).
        *[
            (f"{y}-{md}", code)
            for y in (2027, 2028, 2029)
            for md, code in (
                ("01-01", "new_year"),
                ("04-06", "chakri_day"),
                ("04-13", "songkran"),
                ("04-14", "songkran"),
                ("04-15", "songkran"),
                ("05-01", "labour_day"),
                ("07-28", "king_birthday"),
                ("08-12", "queen_mother_birthday"),
                ("10-13", "king_bhumibol_memorial"),
                ("10-23", "chulalongkorn_day"),
                ("12-05", "king_bhumibol_birthday"),
                ("12-10", "constitution_day"),
                ("12-31", "new_years_eve"),
            )
        ],
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
        ("2027-02-06", "chinese_new_year"),
        ("2027-02-07", "chinese_new_year"),
        ("2027-03-26", "good_friday"),
        ("2027-05-01", "labour_day"),
        ("2027-08-09", "national_day"),
        ("2027-12-25", "christmas_day"),
        ("2028-01-01", "new_year"),
        ("2028-01-26", "chinese_new_year"),
        ("2028-01-27", "chinese_new_year"),
        ("2028-04-14", "good_friday"),
        ("2028-05-01", "labour_day"),
        ("2028-08-09", "national_day"),
        ("2028-12-25", "christmas_day"),
        ("2029-01-01", "new_year"),
        ("2029-02-13", "chinese_new_year"),
        ("2029-02-14", "chinese_new_year"),
        ("2029-03-30", "good_friday"),
        ("2029-05-01", "labour_day"),
        ("2029-08-09", "national_day"),
        ("2029-12-25", "christmas_day"),
    ],
    "us": [
        ("2026-01-01", "new_year"),
        ("2026-05-25", "memorial_day"),
        ("2026-07-04", "independence_day"),
        ("2026-09-07", "labor_day_us"),
        ("2026-11-26", "thanksgiving"),
        ("2026-12-25", "christmas_day"),
        ("2027-01-01", "new_year"),
        ("2027-05-31", "memorial_day"),
        ("2027-07-04", "independence_day"),
        ("2027-09-06", "labor_day_us"),
        ("2027-11-25", "thanksgiving"),
        ("2027-12-25", "christmas_day"),
        ("2028-01-01", "new_year"),
        ("2028-05-29", "memorial_day"),
        ("2028-07-04", "independence_day"),
        ("2028-09-04", "labor_day_us"),
        ("2028-11-23", "thanksgiving"),
        ("2028-12-25", "christmas_day"),
        ("2029-01-01", "new_year"),
        ("2029-05-28", "memorial_day"),
        ("2029-07-04", "independence_day"),
        ("2029-09-03", "labor_day_us"),
        ("2029-11-22", "thanksgiving"),
        ("2029-12-25", "christmas_day"),
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
        ("2027-03-26", "good_friday"),
        ("2027-03-29", "easter_monday"),
        ("2027-05-03", "early_may_bank_holiday"),
        ("2027-05-31", "spring_bank_holiday"),
        ("2027-08-30", "summer_bank_holiday"),
        ("2027-12-25", "christmas_day"),
        ("2027-12-28", "boxing_day_in_lieu"),
        ("2028-01-01", "new_year"),
        ("2028-04-14", "good_friday"),
        ("2028-04-17", "easter_monday"),
        ("2028-05-01", "early_may_bank_holiday"),
        ("2028-05-29", "spring_bank_holiday"),
        ("2028-08-28", "summer_bank_holiday"),
        ("2028-12-25", "christmas_day"),
        ("2029-01-01", "new_year"),
        ("2029-03-30", "good_friday"),
        ("2029-04-02", "easter_monday"),
        ("2029-05-07", "early_may_bank_holiday"),
        ("2029-05-28", "spring_bank_holiday"),
        ("2029-08-27", "summer_bank_holiday"),
        ("2029-12-25", "christmas_day"),
    ],
}

# Dữ liệu phải phủ tối thiểu tới hết năm này cho mọi nước (test kiểm tra); bổ sung trước khi tới.
DATA_COVERED_THROUGH = date(2029, 12, 31)


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
