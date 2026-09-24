import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.analytics.service import AnalyticsService
from app.api.deps import OperatorDep, SessionDep
from app.api.schemas import HealthSummaryOut, ScanRunOut, ScrapeSessionOut
from app.db.models import ScanRun, ScrapeSessionRow
from app.repo.runs import ScanRunRepository

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/summary", response_model=HealthSummaryOut)
async def summary(_: OperatorDep, session: SessionDep) -> HealthSummaryOut:
    now = datetime.now(tz=UTC)
    total, blocked = await ScanRunRepository(session).probe_stats_since(now - timedelta(minutes=15))
    last_run = (
        await session.execute(select(ScanRun).order_by(ScanRun.id.desc()).limit(1))
    ).scalar_one_or_none()
    active = (
        await session.execute(
            select(func.count())
            .select_from(ScrapeSessionRow)
            .where(ScrapeSessionRow.status == "active", ScrapeSessionRow.expires_at > now)
        )
    ).scalar_one()
    pending = await AnalyticsService(session).pending_run_ids()
    return HealthSummaryOut(
        probes_15m=total,
        blocked_15m=blocked,
        block_rate_15m=(blocked / total) if total else 0.0,
        last_run=ScanRunOut.model_validate(last_run) if last_run else None,
        active_sessions=int(active),
        pending_analytics_runs=pending,
        grafana_url=os.environ.get("GRAFANA_URL") or None,
    )


@router.get("/runs", response_model=list[ScanRunOut])
async def runs(
    _: OperatorDep, session: SessionDep, limit: int = Query(20, ge=1, le=200)
) -> list[ScanRun]:
    return list(
        (await session.execute(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit))).scalars()
    )


@router.get("/sessions", response_model=list[ScrapeSessionOut])
async def sessions(
    _: OperatorDep, session: SessionDep, limit: int = Query(50, ge=1, le=500)
) -> list[ScrapeSessionRow]:
    return list(
        (
            await session.execute(
                select(ScrapeSessionRow).order_by(ScrapeSessionRow.created_at.desc()).limit(limit)
            )
        ).scalars()
    )
