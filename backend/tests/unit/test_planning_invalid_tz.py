from datetime import UTC, date, datetime, timedelta

from app.db.models import Tenant
from app.insight.service import due_daily_tenants
from app.repo.runs import HotelJobPlan
from app.scheduler.planning import TenantSchedule, WatchRow, build_hotel_plans, compute_triggers


def test_invalid_timezone_tenant_is_skipped_not_fatal() -> None:
    good = TenantSchedule(1, "Asia/Ho_Chi_Minh", ("06:00",), 30)
    bad = TenantSchedule(2, "Mars/Olympus", ("06:00",), 30)
    now = datetime(2026, 9, 23, 23, 2, tzinfo=UTC)
    triggers = compute_triggers([bad, good], now, timedelta(minutes=10))
    assert [t.tenant_ids for t in triggers] == [(1,)]
    plans = build_hotel_plans(
        [WatchRow(2, 10, 30, "Mars/Olympus"), WatchRow(1, 11, 30, "Asia/Ho_Chi_Minh")],
        datetime(2026, 9, 23, 23, 0, tzinfo=UTC),
    )
    assert plans == [
        HotelJobPlan(10, date(2026, 9, 23), 30),
        HotelJobPlan(11, date(2026, 9, 24), 30),
    ]


def test_due_daily_tenants_skips_invalid_timezone() -> None:
    t = Tenant(
        id=1,
        name="A",
        timezone="Mars/Olympus",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    assert (
        due_daily_tenants([t], datetime(2026, 10, 4, 0, 33, tzinfo=UTC), timedelta(minutes=10))
        == []
    )
