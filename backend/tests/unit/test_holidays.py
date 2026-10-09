from datetime import date

from app.holidays.data import days_to_next_holiday, holidays_between, is_weekend


def test_holidays_between_vn() -> None:
    # Quốc khánh 2026: nghỉ 5 ngày 29/8–2/9 (cùng một đợt).
    hs = holidays_between("VN", date(2026, 8, 25), date(2026, 9, 10))
    assert [h.date for h in hs] == [date(2026, 8, 29 + i) for i in range(3)] + [
        date(2026, 9, 1),
        date(2026, 9, 2),
    ]
    assert {h.group for h in hs} == {"national_day"}
    assert holidays_between("zz", date(2026, 1, 1), date(2026, 12, 31)) == []


def test_culture_day_and_tet_2027() -> None:
    nov = holidays_between("vn", date(2026, 11, 1), date(2026, 11, 30), "vi")
    assert [(h.date, h.name) for h in nov] == [(date(2026, 11, 24), "Ngày Văn hoá Việt Nam")]
    tet = holidays_between("vn", date(2027, 2, 1), date(2027, 2, 15))
    assert [h.date for h in tet] == [date(2027, 2, d) for d in range(4, 11)]
    assert {h.kind for h in tet} == {"tet"} and {h.group for h in tet} == {"tet"}


def test_source_markets_and_seasons() -> None:
    hs = holidays_between(
        "vn", date(2026, 9, 20), date(2026, 10, 2), "en", source_markets=["kr", "cn"]
    )
    kinds = {(h.group, h.kind) for h in hs}
    assert ("kr_chuseok", "source_market") in kinds and ("cn_golden_week", "source_market") in kinds
    assert next(h for h in hs if h.group == "kr_chuseok").name == "Chuseok (Korea)"
    # Không chọn thị trường nguồn thì không có.
    assert all(
        h.kind != "source_market"
        for h in holidays_between("vn", date(2026, 9, 20), date(2026, 10, 2))
    )
    summer = holidays_between("vn", date(2026, 7, 1), date(2026, 7, 2), include_seasons=True)
    assert [h.kind for h in summer] == ["season", "season"]


def test_weekend_is_friday_and_saturday_night() -> None:
    assert is_weekend(date(2026, 10, 2)) and is_weekend(date(2026, 10, 3))  # T6, T7
    assert not is_weekend(date(2026, 10, 4)) and not is_weekend(date(2026, 10, 5))  # CN, T2


def test_next_holiday() -> None:
    assert days_to_next_holiday("vn", date(2026, 8, 27)) == 2
    assert days_to_next_holiday("vn", date(2026, 5, 2), horizon=30) is None
