from datetime import date

from app.holidays.data import days_to_next_holiday, holidays_between, is_weekend


def test_holidays_between_vn() -> None:
    hs = holidays_between("VN", date(2026, 8, 25), date(2026, 9, 10))
    assert [h.date for h in hs] == [date(2026, 9, 2), date(2026, 9, 3)]
    assert holidays_between("zz", date(2026, 1, 1), date(2026, 12, 31)) == []


def test_weekend_and_next_holiday() -> None:
    assert is_weekend(date(2026, 10, 3)) and not is_weekend(date(2026, 10, 5))
    assert days_to_next_holiday("vn", date(2026, 8, 30)) == 3
    assert days_to_next_holiday("vn", date(2026, 5, 2), horizon=30) is None
