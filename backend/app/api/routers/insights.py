from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.deps import ApiQueue, SessionDep, SettingsDep, TenantDep, WriterDep, get_queue
from app.api.schemas import InsightDetailOut, InsightOut
from app.db.models import Insight, Tenant
from app.insight.prompt import PROMPT_VERSION

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", response_model=list[InsightOut])
async def list_insights(
    tenant_id: TenantDep, session: SessionDep, limit: int = Query(30, ge=1, le=200)
) -> list[Insight]:
    return list(
        (
            await session.execute(
                select(Insight)
                .where(Insight.tenant_id == tenant_id)
                .order_by(Insight.generated_at.desc(), Insight.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


@router.get("/{insight_id}", response_model=InsightDetailOut)
async def get_insight(insight_id: int, tenant_id: TenantDep, session: SessionDep) -> Insight:
    row = await session.get(Insight, insight_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "insight not found")
    return row


@router.post("/generate", response_model=InsightOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_insight(
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    queue: Annotated[ApiQueue | None, Depends(get_queue)] = None,
) -> Insight:
    """Tạo bản tin theo yêu cầu: ghi một dòng `pending` rồi đẩy job; dashboard poll trạng thái."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    now = datetime.now(tz=UTC)
    # Dòng pending quá 10 phút nghĩa là jobs worker không chạy: đánh dấu thất bại để không treo mãi.
    await session.execute(
        update(Insight)
        .where(
            Insight.tenant_id == tenant_id,
            Insight.status == "pending",
            Insight.generated_at < now - timedelta(minutes=10),
        )
        .values(status="failed", error="timeout: jobs worker không xử lý trong 10 phút")
    )
    pending = (
        await session.execute(
            select(Insight).where(
                Insight.tenant_id == tenant_id,
                Insight.status == "pending",
                Insight.generated_at >= now - timedelta(minutes=10),
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        return pending
    row = Insight(
        tenant_id=tenant_id,
        period_start=now.date(),
        period_end=now.date() + timedelta(days=tenant.horizon_days - 1),
        generated_at=now,
        trigger="on_demand",
        status="pending",
        model=settings.openai_model,
        prompt_version=PROMPT_VERSION,
        input_json={},
        output_json=None,
        dropped_highlights=[],
    )
    session.add(row)
    await session.commit()
    if queue is None:
        row.status = "failed"
        row.error = "job queue unavailable"
        await session.commit()
        return row
    await queue.enqueue_insight(tenant_id, "on_demand", f"req{row.id}")
    return row
