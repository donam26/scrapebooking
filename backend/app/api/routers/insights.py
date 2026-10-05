from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.deps import (
    ApiQueue,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TenantDep,
    WriterDep,
    get_queue,
)
from app.api.quotas import ensure_can_generate_insight
from app.api.schemas import InsightDetailOut, InsightOut
from app.db.models import Insight, Tenant
from app.insight.prompt import PROMPT_VERSION

router = APIRouter(prefix="/insights", tags=["insights"])

# Người dùng tenant chỉ thấy mã lỗi ngắn (không lộ thông điệp nhà cung cấp/stack); operator
# thấy nguyên văn. Khớp theo tiền tố của `insights.error`, còn lại là lỗi nhà cung cấp.
_PUBLIC_ERROR_CODES: tuple[tuple[str, str], ...] = (
    ("no scan data", "no_scan_data"),
    ("watchlist is empty", "watchlist_empty"),
    ("schema:", "schema_invalid"),
    ("no json output", "schema_invalid"),
    ("timeout:", "worker_timeout"),
    ("job queue unavailable", "queue_unavailable"),
)


def public_error_code(error: str | None) -> str | None:
    if not error:
        return None
    for prefix, code in _PUBLIC_ERROR_CODES:
        if error.startswith(prefix):
            return code
    return "provider_error"


def _out(row: Insight, operator: bool) -> InsightOut:
    out = InsightOut.model_validate(row)
    return out if operator else out.model_copy(update={"error": public_error_code(row.error)})


def _detail_out(row: Insight, operator: bool) -> InsightDetailOut:
    out = InsightDetailOut.model_validate(row)
    return out if operator else out.model_copy(update={"error": public_error_code(row.error)})


@router.get("", response_model=list[InsightOut])
async def list_insights(
    tenant_id: TenantDep,
    principal: PrincipalDep,
    session: SessionDep,
    limit: int = Query(30, ge=1, le=200),
) -> list[InsightOut]:
    rows = (
        await session.execute(
            select(Insight)
            .where(Insight.tenant_id == tenant_id)
            .order_by(Insight.generated_at.desc(), Insight.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [_out(r, principal.is_operator) for r in rows]


@router.get("/{insight_id}", response_model=InsightDetailOut)
async def get_insight(
    insight_id: int, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> InsightDetailOut:
    row = await session.get(Insight, insight_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "insight not found")
    return _detail_out(row, principal.is_operator)


@router.post("/generate", response_model=InsightOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_insight(
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    queue: Annotated[ApiQueue | None, Depends(get_queue)] = None,
) -> InsightOut:
    """Tạo bản tin theo yêu cầu: ghi một dòng `pending` rồi đẩy job; dashboard poll trạng thái."""
    # Khoá dòng tenant tới khi commit: hai lần bấm cùng lúc thì lần sau đợi rồi thấy dòng
    # pending của lần trước, không tạo dòng thứ hai.
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    ).scalar_one_or_none()
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
        (
            await session.execute(
                select(Insight)
                .where(
                    Insight.tenant_id == tenant_id,
                    Insight.status == "pending",
                    Insight.generated_at >= now - timedelta(minutes=10),
                )
                .order_by(Insight.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if pending is not None:
        await session.commit()
        return _out(pending, principal.is_operator)
    if not principal.is_operator:
        await ensure_can_generate_insight(session, settings, tenant_id, now)
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
        return _out(row, principal.is_operator)
    await queue.enqueue_insight(tenant_id, "on_demand", f"req{row.id}")
    return _out(row, principal.is_operator)
