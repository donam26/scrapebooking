"""Tạo đợt quét thủ công (tenant hoặc toàn hệ thống) và đẩy job vào hàng đợi."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiQueue
from app.db.models import ScanRun, Tenant, TenantHotel
from app.repo.runs import ScanRunRepository
from app.scheduler.planning import WatchRow, build_hotel_plans

DEDUP_WINDOW = timedelta(minutes=10)


async def create_manual_run(
    session: AsyncSession, queue: ApiQueue | None, tenant_id: int | None
) -> ScanRun:
    """Đợt quét thủ công cho một tenant (tenant_id) hoặc mọi tenant đang hoạt động (None).

    Trong 10 phút, gọi lại trả về đợt đang chạy thay vì tạo thêm (tránh quét trùng).
    """
    if queue is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable")
    now = datetime.now(tz=UTC)
    prefix = f"manual:t{tenant_id}:" if tenant_id is not None else "manual:all:"
    recent = (
        await session.execute(
            select(ScanRun)
            .where(
                ScanRun.trigger_key.like(prefix + "%"),
                ScanRun.status == "running",
                ScanRun.scheduled_at >= now - DEDUP_WINDOW,
            )
            .order_by(ScanRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if recent is not None:
        return recent
    stmt = (
        select(TenantHotel.tenant_id, TenantHotel.hotel_id, Tenant.horizon_days, Tenant.timezone)
        .join(Tenant, Tenant.id == TenantHotel.tenant_id)
        .where(TenantHotel.active.is_(True), Tenant.active.is_(True))
    )
    if tenant_id is not None:
        stmt = stmt.where(TenantHotel.tenant_id == tenant_id)
    plans = build_hotel_plans([WatchRow(*r) for r in await session.execute(stmt)], now)
    if not plans:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "watchlist is empty")
    run = await ScanRunRepository(session).create_run(f"{prefix}{now:%Y%m%dT%H%M%S}", now, plans)
    if run is None:  # trùng khoá trong cùng giây
        raise HTTPException(status.HTTP_409_CONFLICT, "scan run already created")
    await session.commit()
    for plan in plans:
        await queue.enqueue_probe(run.id, plan.hotel_id)
    return run
