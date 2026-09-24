import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.pms.base import PmsAdapterError
from app.pms.csv_adapter import CsvAdapter, parse_date, parse_decimal, parse_int, template_csv


def test_template_matches_canonical_columns() -> None:
    header = template_csv().splitlines()[0]
    assert header == "stay_date,rooms_total,rooms_sold,rooms_available,occupancy_pct,adr,revenue"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-10-01", date(2026, 10, 1)),
        ("01/10/2026", date(2026, 10, 1)),
        ("1.10.2026", date(2026, 10, 1)),
    ],
)
def test_parse_date(text: str, expected: date) -> None:
    assert parse_date(text) == expected


def test_parse_numbers() -> None:
    assert parse_int("1,200") == 1200 and parse_int("") is None
    assert parse_decimal("85.5%") == Decimal("85.5")
    assert parse_decimal("1.234.567,89") == Decimal("1234567.89")
    assert parse_decimal("1,234,567.89") == Decimal("1234567.89")
    with pytest.raises(ValueError):
        parse_int("1.5")


def test_template_roundtrip_and_derived_fields() -> None:
    ad = CsvAdapter()
    table = ad.read_table(template_csv().encode(), "template.csv")
    mapping = ad.suggest_mapping(table.columns)
    assert mapping == {c: c for c in table.columns}
    rows, errors = ad.parse(table, mapping)
    assert errors == [] and len(rows) == 2
    assert rows[0].stay_date == date(2026, 10, 1) and rows[0].occupancy_pct == Decimal("80.0")
    assert rows[0].adr == Decimal("1850000")


def test_semicolon_csv_with_aliases_and_row_errors() -> None:
    ad = CsvAdapter()
    content = b"Date;Rooms;Sold;Occ %\n2026-10-01;100;80;80\n2026-10-02;100;120;120\n2026-10-01;100;50;50\nnope;1;1;1\n"
    table = ad.read_table(content, "x.csv")
    assert table.columns == ["Date", "Rooms", "Sold", "Occ %"]
    mapping = ad.suggest_mapping(table.columns)
    assert mapping == {
        "stay_date": "Date",
        "rooms_total": "Rooms",
        "rooms_sold": "Sold",
        "occupancy_pct": "Occ %",
    }
    rows, errors = ad.parse(table, mapping)
    assert len(rows) == 1 and rows[0].rooms_available == 20
    assert [(e.row, e.column) for e in errors] == [
        (2, "occupancy_pct"),
        (3, "stay_date"),
        (4, "stay_date"),
    ]


def test_missing_required_mapping() -> None:
    ad = CsvAdapter()
    table = ad.read_table(b"a,b\n1,2\n", "x.csv")
    rows, errors = ad.parse(table, {})
    assert rows == [] and errors[0].column == "stay_date"


def test_excel_input() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Ngày", "Tổng phòng", "Phòng bán", "Doanh thu"])
    ws.append([date(2026, 10, 1), 50, 40, 90000000])
    ws.append([None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    ad = CsvAdapter()
    table = ad.read_table(buf.getvalue(), "occ.xlsx")
    mapping = ad.suggest_mapping(table.columns)
    rows, errors = ad.parse(table, mapping)
    assert errors == [] and len(rows) == 1
    assert rows[0].rooms_available == 10 and rows[0].occupancy_pct == Decimal("80.00")
    assert rows[0].revenue == Decimal("90000000")


def test_garbage_file() -> None:
    with pytest.raises(PmsAdapterError):
        CsvAdapter().read_table(b"", "x.csv")
