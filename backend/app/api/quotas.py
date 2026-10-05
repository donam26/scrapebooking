"""Hạn mức theo tenant: mặc định từ cấu hình, ghi đè bằng `tenants.limits` (JSONB, operator đặt).
Dùng để một tenant không chiếm hết ngân sách request/proxy/token của cả hệ thống."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Insight, ScanRun, Tenant, TenantHotel

LIMIT_KEYS = ("max_hotels", "manual_scans_per_day", "insights_per_day")


@dataclass(frozen=True)
class TenantLimits:
    max_hotels: int
    manual_scans_per_day: int
    insights_per_day: int


def limits_for(settings: Settings, overrides: dict[str, Any] | None) -> TenantLimits:
    o = overrides or {}

    def pick(key: str, default: int) -> int:
        value = o.get(key)
        return int(value) if isinstance(value, int) and value >= 0 else default

    return TenantLimits(
        max_hotels=pick("max_hotels", settings.quota_max_hotels),
        manual_scans_per_day=pick("manual_scans_per_day", settings.quota_manual_scans_per_day),
        insights_per_day=pick("insights_per_day", settings.quota_insights_per_day),
    )


async def tenant_limits(session: AsyncSession, settings: Settings, tenant_id: int) -> TenantLimits:
    overrides = (
        await session.execute(select(Tenant.limits).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    return limits_for(settings, overrides)


def _quota_error(what: str, limit: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"quota exceeded: {what} (limit {limit}); contact the operator to raise it",
    )


async def ensure_can_add_hotel(session: AsyncSession, settings: Settings, tenant_id: int) -> None:
    limits = await tenant_limits(session, settings, tenant_id)
    count = (
        await session.execute(
            select(func.count())
            .select_from(TenantHotel)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
        )
    ).scalar_one()
    if count >= limits.max_hotels:
        raise _quota_error("hotels in watchlist", limits.max_hotels)


async def ensure_can_scan_now(
    session: AsyncSession, settings: Settings, tenant_id: int, now: datetime | None = None
) -> None:
    """Đếm lần bấm "Quét ngay" của tenant trong 24 giờ qua: một lần bấm tạo một run mỗi kênh
    (khoá `manual:t<id>[:h<hotel>]:<thời điểm>:<kênh>`), bỏ hậu tố kênh để đếm theo lần bấm."""
    limits = await tenant_limits(session, settings, tenant_id)
    since = (now or datetime.now(tz=UTC)) - timedelta(hours=24)
    action_key = func.regexp_replace(ScanRun.trigger_key, ":[a-z]+$", "")
    count = (
        await session.execute(
            select(func.count(func.distinct(action_key)))
            .select_from(ScanRun)
            .where(
                ScanRun.trigger_key.like(f"manual:t{tenant_id}:%"),
                ScanRun.scheduled_at >= since,
            )
        )
    ).scalar_one()
    if count >= limits.manual_scans_per_day:
        raise _quota_error("manual scans per day", limits.manual_scans_per_day)


async def ensure_can_generate_insight(
    session: AsyncSession, settings: Settings, tenant_id: int, now: datetime | None = None
) -> None:
    limits = await tenant_limits(session, settings, tenant_id)
    since = (now or datetime.now(tz=UTC)) - timedelta(hours=24)
    count = (
        await session.execute(
            select(func.count())
            .select_from(Insight)
            .where(
                Insight.tenant_id == tenant_id,
                Insight.trigger == "on_demand",
                Insight.generated_at >= since,
            )
        )
    ).scalar_one()
    if count >= limits.insights_per_day:
        raise _quota_error("on-demand insights per day", limits.insights_per_day)
