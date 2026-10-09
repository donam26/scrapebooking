"""Lịch cầu tĩnh (spec mục 4: holidays/): ngày lễ theo nước của tenant, lễ của thị trường nguồn
khách (roadmap 7.5) và mùa du lịch. Bổ sung khi onboard tenant nước mới.

Ngày âm lịch (Tết, Giỗ Tổ, Seollal, Chuseok…) ghi theo dương lịch của từng năm.

**Quy trình cập nhật mỗi năm (Việt Nam):** Bộ Nội vụ / Văn phòng Chính phủ công bố phương án nghỉ
Tết, 30/4–1/5, 2/9, 24/11 (thường tháng 9–11 năm trước). Ghi **mọi ngày được nghỉ** của đợt
(kể cả cuối tuần và ngày hoán đổi) vào cùng `group` để giao diện gộp thành một khoảng và nhịp/gợi
ý giá biết đêm đó là đêm lễ. Nguồn đã dùng:
- 2/9/2026: nghỉ 29/8–2/9 (Bộ Nội vụ, xaydungchinhsach.chinhphu.vn, 07/2026).
- 24/11/2026 "Ngày Văn hoá Việt Nam": nghỉ 1 ngày; Tết 2027 nghỉ 04–10/02/2027; 2/9/2027 nghỉ
  02–05/09/2027 (VPCP 10065/VPCP-KGVX ngày 02/10/2026).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.i18n import DEFAULT_LOCALE, t

# tet: Tết/năm mới âm lịch; travel: không phải ngày nghỉ nhưng cầu du lịch cao; holiday: còn lại;
# source_market: kỳ nghỉ của thị trường nguồn khách (Hàn, Trung, Nhật…); season: mùa du lịch.
HolidayKind = Literal["tet", "holiday", "travel", "source_market", "season"]

# Thị trường nguồn khách có lịch (mã nước ISO): tenant chọn trong Cài đặt.
SOURCE_MARKETS = ("cn", "kr", "jp", "tw", "ru", "in", "us", "au")


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
    "tet_break": "tet",
    "national_day_in_lieu": "national_day",
    "national_day_break": "national_day",
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
        # Quốc khánh 2026: nghỉ 5 ngày 29/8–2/9 (hoán đổi thứ Hai 31/8 sang thứ Bảy 22/8).
        ("2026-08-29", "national_day_break"),
        ("2026-08-30", "national_day_break"),
        ("2026-08-31", "national_day_break"),
        ("2026-09-01", "national_day_in_lieu"),
        ("2026-09-02", "national_day"),
        ("2026-11-24", "culture_day"),  # Ngày Văn hoá Việt Nam, nghỉ 1 ngày (từ 2026)
        ("2026-12-25", "christmas_vn"),
        ("2027-01-01", "new_year"),
        # Tết Đinh Mùi 2027: nghỉ 04/02 (28 Chạp) – 10/02 (mùng 5).
        ("2027-02-04", "tet_break"),
        ("2027-02-05", "tet_eve"),
        ("2027-02-06", "tet_1"),
        ("2027-02-07", "tet_2"),
        ("2027-02-08", "tet_3"),
        ("2027-02-09", "tet_4"),
        ("2027-02-10", "tet_break"),
        ("2027-04-16", "hung_kings"),
        ("2027-04-30", "reunification"),
        ("2027-05-01", "labour_day"),
        # Quốc khánh 2027: nghỉ 02–05/09.
        ("2027-09-02", "national_day"),
        ("2027-09-03", "national_day_in_lieu"),
        ("2027-09-04", "national_day_break"),
        ("2027-09-05", "national_day_break"),
        ("2027-11-24", "culture_day"),
        ("2027-12-25", "christmas_vn"),
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

# Kỳ nghỉ của thị trường nguồn khách (khoảng ngày, mã đợt): đẩy cầu tới điểm đến Việt Nam.
# Tên đọc từ `holiday.sm_<mã>`. Chỉ hiện khi tenant chọn thị trường đó. Ngày âm lịch và lịch nghỉ
# nước ngoài năm sau chưa công bố chính thức thì ghi theo lịch truyền thống (cập nhật khi có).
_SOURCE_MARKET: dict[str, list[tuple[str, str, str]]] = {
    "cn": [
        ("2026-02-15", "2026-02-23", "cn_spring_festival"),
        ("2026-05-01", "2026-05-05", "cn_labour_day"),
        ("2026-10-01", "2026-10-07", "cn_golden_week"),
        ("2027-02-05", "2027-02-13", "cn_spring_festival"),
        ("2027-05-01", "2027-05-05", "cn_labour_day"),
        ("2027-10-01", "2027-10-07", "cn_golden_week"),
    ],
    "kr": [
        ("2026-02-14", "2026-02-18", "kr_seollal"),
        ("2026-09-24", "2026-09-27", "kr_chuseok"),
        ("2026-12-24", "2027-01-01", "kr_year_end"),
        ("2027-02-06", "2027-02-09", "kr_seollal"),
        ("2027-09-14", "2027-09-16", "kr_chuseok"),
    ],
    "jp": [
        ("2026-04-29", "2026-05-06", "jp_golden_week"),
        ("2026-08-13", "2026-08-16", "jp_obon"),
        ("2026-12-29", "2027-01-03", "jp_new_year"),
        ("2027-04-29", "2027-05-05", "jp_golden_week"),
        ("2027-08-13", "2027-08-16", "jp_obon"),
    ],
    "tw": [
        ("2026-02-14", "2026-02-22", "tw_lunar_new_year"),
        ("2026-10-09", "2026-10-11", "tw_double_ten"),
        ("2027-02-05", "2027-02-10", "tw_lunar_new_year"),
    ],
    "ru": [
        ("2026-12-31", "2027-01-10", "ru_new_year"),
        ("2027-12-31", "2028-01-08", "ru_new_year"),
    ],
    "in": [
        ("2026-11-06", "2026-11-10", "in_diwali"),
        ("2026-12-20", "2027-01-02", "in_winter_break"),
        ("2027-10-27", "2027-10-31", "in_diwali"),
    ],
    "us": [
        ("2026-11-25", "2026-11-29", "us_thanksgiving"),
        ("2026-12-19", "2027-01-03", "us_winter_break"),
    ],
    "au": [
        ("2026-09-19", "2026-10-05", "au_spring_school_break"),
        ("2026-12-18", "2027-01-27", "au_summer_school_break"),
    ],
}

# Mùa du lịch trong nước (Việt Nam): nghỉ hè học sinh.
_SEASONS: dict[str, list[tuple[str, str, str]]] = {
    "vn": [
        ("2026-06-01", "2026-08-15", "vn_summer_holiday"),
        ("2027-06-01", "2027-08-15", "vn_summer_holiday"),
    ],
}


def _expand(
    ranges: list[tuple[str, str, str]], start: date, end: date
) -> Iterable[tuple[date, str]]:
    for a, b, code in ranges:
        d, last = max(date.fromisoformat(a), start), date.fromisoformat(b)
        while d <= min(last, end):
            yield d, code
            d += timedelta(days=1)


_KIND_ORDER = {"tet": 0, "holiday": 1, "travel": 2, "source_market": 3, "season": 4}


def holidays_between(
    country: str,
    start: date,
    end: date,
    locale: str = DEFAULT_LOCALE,
    source_markets: Iterable[str] = (),
    include_seasons: bool = False,
) -> list[Holiday]:
    """Ngày lễ của nước tenant trong [start, end]; thêm kỳ nghỉ của `source_markets` (thị trường
    nguồn tenant chọn) và mùa du lịch khi yêu cầu. Nhịp đặt phòng chỉ dùng ngày lễ của nước."""
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
    for market in sorted({m.lower() for m in source_markets}):
        for d, code in _expand(_SOURCE_MARKET.get(market, []), start, end):
            out.append(Holiday(d, t(locale, f"holiday.sm_{code}"), market, "source_market", code))
    if include_seasons:
        for d, code in _expand(_SEASONS.get(country.lower(), []), start, end):
            out.append(Holiday(d, t(locale, f"holiday.sm_{code}"), country.lower(), "season", code))
    return sorted(out, key=lambda h: (h.date, _KIND_ORDER[h.kind], h.group))


def is_weekend(d: date) -> bool:
    """Đêm cuối tuần của khách sạn: đêm thứ Sáu và thứ Bảy (khách nhận phòng T6/T7)."""
    return d.weekday() in (4, 5)


def days_to_next_holiday(country: str, d: date, horizon: int = 60) -> int | None:
    for h in holidays_between(country, d, d + timedelta(days=horizon)):
        return (h.date - d).days
    return None
