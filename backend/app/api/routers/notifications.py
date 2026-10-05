"""Cài đặt thông báo email của tenant: người nhận, loại thông báo, gửi thử, nhật ký đã gửi."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, delete, func, not_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import PrincipalDep, SessionDep, SettingsDep, TenantDep, WriterDep
from app.api.schemas import (
    NotificationLogOut,
    NotificationRuleOut,
    NotificationRuleUpdate,
    NotificationSettingsOut,
    RecipientCreate,
    RecipientOut,
)
from app.config import Settings
from app.db.models import Notification, NotificationRecipient, Tenant
from app.notify.email_sender import EmailSender, SmtpEmailSender
from app.notify.kinds import InvalidParams, NotificationKind, normalize_params
from app.notify.service import (
    SKIP_DISABLED,
    SKIP_NO_MATCHES,
    NotificationService,
    TestTooSoon,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

MAX_RECIPIENTS = 20


def get_email_sender(request: Request, settings: SettingsDep) -> EmailSender:
    """Test gắn sender giả vào `app.state.email_sender`; production dùng SMTP theo cấu hình."""
    sender: EmailSender | None = getattr(request.app.state, "email_sender", None)
    return sender or SmtpEmailSender(settings)


SenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def _service(session: SessionDep, sender: EmailSender, settings: Settings) -> NotificationService:
    return NotificationService(session, sender, settings)


@router.get("/settings", response_model=NotificationSettingsOut)
async def get_settings_(
    tenant_id: TenantDep, session: SessionDep, sender: SenderDep, settings: SettingsDep
) -> NotificationSettingsOut:
    svc = _service(session, sender, settings)
    recipients = (
        await session.execute(
            select(NotificationRecipient)
            .where(NotificationRecipient.tenant_id == tenant_id)
            .order_by(NotificationRecipient.id)
        )
    ).scalars()
    rules = await svc.rules(tenant_id)
    return NotificationSettingsOut(
        email_configured=sender.configured,
        recipients=[RecipientOut.model_validate(r) for r in recipients],
        rules=[
            NotificationRuleOut(kind=str(k), active=r.active, params=r.params)
            for k, r in rules.items()
        ],
    )


@router.post("/recipients", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def add_recipient(
    body: RecipientCreate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> RecipientOut:
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    count = (
        await session.execute(
            select(func.count()).where(NotificationRecipient.tenant_id == tenant_id)
        )
    ).scalar_one()
    if count >= MAX_RECIPIENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"at most {MAX_RECIPIENTS} recipients"
        )
    row = NotificationRecipient(tenant_id=tenant_id, email=str(body.email).strip(), active=True)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "recipient already exists") from exc
    await session.refresh(row)
    return RecipientOut.model_validate(row)


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recipient(
    recipient_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> None:
    result = await session.execute(
        delete(NotificationRecipient).where(
            NotificationRecipient.id == recipient_id,
            NotificationRecipient.tenant_id == tenant_id,
        )
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipient not found")
    await session.commit()


@router.put("/rules/{kind}", response_model=NotificationRuleOut)
async def update_rule(
    kind: NotificationKind,
    body: NotificationRuleUpdate,
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    sender: SenderDep,
    settings: SettingsDep,
) -> NotificationRuleOut:
    try:
        params = normalize_params(kind, body.params)
    except InvalidParams as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await _service(session, sender, settings).mark_rule(tenant_id, kind, body.active, params)
    await session.commit()
    return NotificationRuleOut(kind=str(kind), active=body.active, params=params)


def _log_out(row: Notification, operator: bool) -> NotificationLogOut:
    reason = (
        row.detail
        if row.status == "skipped"
        else ("send_failed" if row.status == "failed" else None)
    )
    return NotificationLogOut(
        id=row.id,
        kind=row.kind,
        status=row.status,
        subject=row.subject,
        item_count=row.item_count,
        recipients=list(row.recipients or []),
        reason=reason,
        detail=row.detail if operator and row.status != "skipped" else None,
        created_at=row.created_at,
        sent_at=row.sent_at,
    )


@router.post("/test", response_model=NotificationLogOut)
async def send_test(
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    sender: SenderDep,
    settings: SettingsDep,
) -> NotificationLogOut:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    try:
        row = await _service(session, sender, settings).send_test(tenant)
    except TestTooSoon as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "test email sent less than a minute ago"
        ) from exc
    return _log_out(row, principal.is_operator)


@router.get("/log", response_model=list[NotificationLogOut])
async def notification_log(
    tenant_id: TenantDep,
    principal: PrincipalDep,
    session: SessionDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[NotificationLogOut]:
    # Dòng "không có gì để báo" và "loại thông báo đang tắt" chỉ để chống tính lại, không hiện.
    rows = (
        await session.execute(
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                not_(
                    and_(
                        Notification.status == "skipped",
                        Notification.detail.in_([SKIP_NO_MATCHES, SKIP_DISABLED]),
                    )
                ),
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [_log_out(r, principal.is_operator) for r in rows]
