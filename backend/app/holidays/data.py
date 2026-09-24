"""Bảng ngày lễ tĩnh theo nước (spec mục 4: holidays/). Bổ sung khi onboard tenant nước mới.

Ngày âm lịch (Tết, Giỗ Tổ) ghi theo dương lịch của từng năm.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Holiday:
    date: date
    name: str
    country: str


_HOLIDAYS: dict[str, list[tuple[str, str]]] = {
    "vn": [
        ("2026-01-01", "Tết Dương lịch"),
        ("2026-02-16", "Tết Nguyên đán (29 Tết)"),
        ("2026-02-17", "Tết Nguyên đán (Mùng 1)"),
        ("2026-02-18", "Tết Nguyên đán (Mùng 2)"),
        ("2026-02-19", "Tết Nguyên đán (Mùng 3)"),
        ("2026-02-20", "Tết Nguyên đán (Mùng 4)"),
        ("2026-04-26", "Giỗ Tổ Hùng Vương"),
        ("2026-04-30", "Ngày Giải phóng miền Nam"),
        ("2026-05-01", "Quốc tế Lao động"),
        ("2026-09-02", "Quốc khánh"),
        ("2026-09-03", "Quốc khánh (nghỉ bù)"),
        ("2026-12-25", "Giáng sinh (không nghỉ, cầu du lịch)"),
        ("2027-01-01", "Tết Dương lịch"),
        ("2027-02-05", "Tết Nguyên đán (29 Tết)"),
        ("2027-02-06", "Tết Nguyên đán (Mùng 1)"),
        ("2027-02-07", "Tết Nguyên đán (Mùng 2)"),
        ("2027-02-08", "Tết Nguyên đán (Mùng 3)"),
        ("2027-02-09", "Tết Nguyên đán (Mùng 4)"),
        ("2027-04-16", "Giỗ Tổ Hùng Vương"),
        ("2027-04-30", "Ngày Giải phóng miền Nam"),
        ("2027-05-01", "Quốc tế Lao động"),
        ("2027-09-02", "Quốc khánh"),
    ],
    "th": [
        ("2026-01-01", "New Year's Day"),
        ("2026-04-06", "Chakri Day"),
        ("2026-04-13", "Songkran"),
        ("2026-04-14", "Songkran"),
        ("2026-04-15", "Songkran"),
        ("2026-05-01", "Labour Day"),
        ("2026-07-28", "King's Birthday"),
        ("2026-08-12", "Queen Mother's Birthday"),
        ("2026-10-13", "King Bhumibol Memorial Day"),
        ("2026-10-23", "Chulalongkorn Day"),
        ("2026-12-05", "King Bhumibol's Birthday"),
        ("2026-12-10", "Constitution Day"),
        ("2026-12-31", "New Year's Eve"),
        ("2027-01-01", "New Year's Day"),
    ],
    "sg": [
        ("2026-01-01", "New Year's Day"),
        ("2026-02-17", "Chinese New Year"),
        ("2026-02-18", "Chinese New Year"),
        ("2026-04-03", "Good Friday"),
        ("2026-05-01", "Labour Day"),
        ("2026-08-09", "National Day"),
        ("2026-12-25", "Christmas Day"),
        ("2027-01-01", "New Year's Day"),
    ],
    "us": [
        ("2026-01-01", "New Year's Day"),
        ("2026-05-25", "Memorial Day"),
        ("2026-07-04", "Independence Day"),
        ("2026-09-07", "Labor Day"),
        ("2026-11-26", "Thanksgiving"),
        ("2026-12-25", "Christmas Day"),
        ("2027-01-01", "New Year's Day"),
    ],
    "gb": [
        ("2026-01-01", "New Year's Day"),
        ("2026-04-03", "Good Friday"),
        ("2026-04-06", "Easter Monday"),
        ("2026-05-04", "Early May bank holiday"),
        ("2026-05-25", "Spring bank holiday"),
        ("2026-08-31", "Summer bank holiday"),
        ("2026-12-25", "Christmas Day"),
        ("2026-12-28", "Boxing Day (substitute)"),
        ("2027-01-01", "New Year's Day"),
    ],
}


def holidays_between(country: str, start: date, end: date) -> list[Holiday]:
    out = []
    for iso, name in _HOLIDAYS.get(country.lower(), []):
        d = date.fromisoformat(iso)
        if start <= d <= end:
            out.append(Holiday(d, name, country.lower()))
    return sorted(out, key=lambda h: h.date)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def days_to_next_holiday(country: str, d: date, horizon: int = 60) -> int | None:
    for h in holidays_between(country, d, d + timedelta(days=horizon)):
        return (h.date - d).days
    return None
