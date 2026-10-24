from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.auth import Principal
from app.api.deps import (
    ApiQueue,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TenantDep,
    WriterDep,
    get_queue,
)
from app.api.schemas import InsightDetailOut, InsightOut
from app.db.models import Insight, Tenant
from app.insight.prompt import PROMPT_VERSION
from app.insight.service import is_placeholder, placeholder_clause

router = APIRouter(prefix="/insights", tags=["insights"])


# Tenant chỉ thấy bản tin đang tạo và bản tin thật đã xong; bản lỗi và đầu ra giả (thiếu
# OPENROUTER_API_KEY) chỉ operator thấy (audit L2/F4).
_TENANT_VISIBLE = ("pending", "batch_pending", "completed")


def _for_viewer[T: InsightOut](out: T, principal: Principal) -> T:
    """Bản tenant xem: không lộ lỗi nội bộ; đầu ra giả coi như tạo không thành công."""
    if principal.is_operator:
        return out
    update: dict[str, object] = {"error": None}
    if out.status == "completed" and is_placeholder(out.model, out.output_json):
        update.update(status="failed", output_json=None)
    return out.model_copy(update=update)


@router.get("", response_model=list[InsightOut])
async def list_insights(
    tenant_id: TenantDep,
    principal: PrincipalDep,
    session: SessionDep,
    limit: int = Query(30, ge=1, le=200),
) -> list[Insight]:
    q = select(Insight).where(Insight.tenant_id == tenant_id)
    if not principal.is_operator:
        q = q.where(Insight.status.in_(_TENANT_VISIBLE), ~placeholder_clause())
    return list(
        (
            await session.execute(
                q.order_by(Insight.generated_at.desc(), Insight.id.desc()).limit(limit)
            )
        ).scalars()
    )


@router.get("/{insight_id}", response_model=InsightDetailOut)
async def get_insight(
    insight_id: int, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> InsightDetailOut:
    """Tenant vẫn đọc được bản lỗi/giả theo id (để màn hình đang chờ biết là đã dừng), nhưng chỉ
    thấy trạng thái "failed", không thấy lỗi nội bộ hay nội dung giả."""
    row = await session.get(Insight, insight_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "insight not found")
    return _for_viewer(InsightDetailOut.model_validate(row), principal)


@router.post("/generate", response_model=InsightOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_insight(
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    queue: Annotated[ApiQueue | None, Depends(get_queue)] = None,
) -> InsightOut:
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
        .values(status="failed", error="timeout: jobs worker did not pick it up within 10 minutes")
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
        return _for_viewer(InsightOut.model_validate(pending), principal)
    row = Insight(
        tenant_id=tenant_id,
        period_start=now.date(),
        period_end=now.date() + timedelta(days=tenant.horizon_days - 1),
        generated_at=now,
        trigger="on_demand",
        status="pending",
        model=settings.openrouter_model,
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
        return _for_viewer(InsightOut.model_validate(row), principal)
    await queue.enqueue_insight(tenant_id, "on_demand", f"req{row.id}")
    return _for_viewer(InsightOut.model_validate(row), principal)
