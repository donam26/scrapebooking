from datetime import date

from app.db.partitions import month_range, partition_name


def test_partition_name() -> None:
    assert partition_name(date(2026, 9, 15)) == "room_snapshots_2026_09"


def test_month_range_crosses_year() -> None:
    assert month_range(date(2026, 12, 3)) == (date(2026, 12, 1), date(2027, 1, 1))
