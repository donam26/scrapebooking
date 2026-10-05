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


def test_every_country_has_data_through_the_declared_horizon() -> None:
    # Lễ chỉ có trong bảng tĩnh: hết dữ liệu là bản tin/heatmap âm thầm mất lớp ngày lễ.
    from app.holidays.data import _HOLIDAYS, DATA_COVERED_THROUGH

    assert DATA_COVERED_THROUGH >= date(2029, 12, 31)
    for country, rows in _HOLIDAYS.items():
        last = max(date.fromisoformat(iso) for iso, _ in rows)
        assert last >= date(DATA_COVERED_THROUGH.year, 12, 1), country
        assert len(set(rows)) == len(rows), f"duplicate holiday rows for {country}"


def test_tet_2028_and_2029_dates() -> None:
    tet_28 = [
        h for h in holidays_between("vn", date(2028, 1, 20), date(2028, 2, 5)) if h.group == "tet"
    ]
    assert [h.date for h in tet_28][:2] == [date(2028, 1, 25), date(2028, 1, 26)]
    tet_29 = [
        h for h in holidays_between("vn", date(2029, 2, 1), date(2029, 2, 28)) if h.group == "tet"
    ]
    assert tet_29[1].date == date(2029, 2, 13)
