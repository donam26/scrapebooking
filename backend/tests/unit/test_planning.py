from datetime import UTC, date, datetime, timedelta

from app.repo.runs import HotelJobPlan
from app.scheduler.planning import TenantSchedule, WatchRow, build_hotel_plans, compute_triggers

VN = TenantSchedule(
    id=1, timezone="Asia/Ho_Chi_Minh", scan_times=("06:00", "14:00", "22:00"), horizon_days=30
)
BKK = TenantSchedule(id=2, timezone="Asia/Bangkok", scan_times=("06:00",), horizon_days=45)
LON = TenantSchedule(id=3, timezone="Europe/London", scan_times=("06:00",), horizon_days=30)


def test_trigger_due_within_lookback() -> None:
    now = datetime(2026, 9, 23, 23, 3, tzinfo=UTC)  # 06:03 giờ VN ngày 24/09
    triggers = compute_triggers([VN], now, lookback=timedelta(minutes=10))
    assert len(triggers) == 1
    t = triggers[0]
    assert t.key == "2026-09-23T23:00"
    assert t.at == datetime(2026, 9, 23, 23, 0, tzinfo=UTC)
    assert t.tenant_ids == (1,)


def test_no_trigger_outside_lookback() -> None:
    now = datetime(2026, 9, 23, 23, 15, tzinfo=UTC)
    assert compute_triggers([VN], now, lookback=timedelta(minutes=10)) == []


def test_tenants_in_same_utc_minute_share_trigger() -> None:
    now = datetime(2026, 9, 23, 23, 1, tzinfo=UTC)
    triggers = compute_triggers([VN, BKK], now, lookback=timedelta(minutes=10))
    assert len(triggers) == 1 and triggers[0].tenant_ids == (1, 2)


def test_different_timezones_get_different_triggers() -> None:
    now = datetime(2026, 9, 24, 5, 2, tzinfo=UTC)  # 06:02 London (BST) ngày 24/09
    triggers = compute_triggers([VN, LON], now, lookback=timedelta(minutes=10))
    assert [t.tenant_ids for t in triggers] == [(3,)]


def test_build_hotel_plans_merges_horizon_and_start_date() -> None:
    at = datetime(2026, 9, 23, 23, 0, tzinfo=UTC)
    rows = [
        WatchRow(tenant_id=1, hotel_id=10, horizon_days=30, timezone="Asia/Ho_Chi_Minh"),
        WatchRow(tenant_id=2, hotel_id=10, horizon_days=45, timezone="Asia/Bangkok"),
        WatchRow(tenant_id=2, hotel_id=11, horizon_days=45, timezone="Asia/Bangkok"),
        WatchRow(tenant_id=3, hotel_id=12, horizon_days=30, timezone="America/New_York"),
    ]
    plans = build_hotel_plans(rows, at)
    assert plans == [
        HotelJobPlan(10, date(2026, 9, 24), 45),
        HotelJobPlan(11, date(2026, 9, 24), 45),
        HotelJobPlan(12, date(2026, 9, 23), 30),
    ]
