"""Cài đặt thông báo của tenant: người nhận email, đăng ký theo người (email/Zalo/webhook), loại
thông báo, gửi thử, nhật ký đã gửi, theo dõi lượt nhấn và "Đã xử lý" (roadmap Phase 3)."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, delete, func, not_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import PrincipalDep, SessionDep, SettingsDep, TenantDep, WriterDep
from app.api.schemas import (
    EngagementOut,
    EngagementWeekOut,
    NotificationLogOut,
    NotificationRuleOut,
    NotificationRuleUpdate,
    NotificationSettingsOut,
    RecipientCreate,
    RecipientOut,
    SubscriptionIn,
    SubscriptionOut,
)
from app.config import Settings
from app.db.models import (
    Notification,
    NotificationDelivery,
    NotificationRecipient,
    NotificationSubscription,
    Tenant,
)
from app.notify.channels import normalize_vn_phone
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
        zalo_configured=settings.zalo_zns_configured,
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
        channel=row.channel or "email",
        resolved_at=row.resolved_at,
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


# ---- đăng ký theo người (3.4) ------------------------------------------------------------------

MAX_SUBSCRIPTIONS = 50
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_target(body: SubscriptionIn) -> str:
    target = body.target.strip()
    if body.channel == "email" and not _EMAIL_RE.match(target):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid email")
    if body.channel == "zalo":
        phone = normalize_vn_phone(target)
        if phone is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid Vietnamese phone number"
            )
        return phone
    if body.channel == "webhook" and not target.startswith("https://"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "webhook must be https://")
    return target


def _sub_out(r: NotificationSubscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=r.id,
        user_id=r.user_id,
        channel=r.channel,
        target=r.target,
        kinds=list(r.kinds or []),
        quiet_start=r.quiet_start,
        quiet_end=r.quiet_end,
        max_per_day=r.max_per_day,
        active=r.active,
        created_at=r.created_at,
    )


async def _own_sub(
    session: SessionDep, tenant_id: int, sub_id: int, principal: PrincipalDep
) -> NotificationSubscription:
    row = await session.get(NotificationSubscription, sub_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subscription not found")
    if not principal.can_write and row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your subscription")
    return row


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> list[SubscriptionOut]:
    """Quản trị tenant thấy mọi đăng ký; người xem chỉ thấy đăng ký của mình."""
    stmt = select(NotificationSubscription).where(NotificationSubscription.tenant_id == tenant_id)
    if not principal.can_write:
        stmt = stmt.where(NotificationSubscription.user_id == principal.user_id)
    rows = (await session.execute(stmt.order_by(NotificationSubscription.id))).scalars()
    return [_sub_out(r) for r in rows]


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionIn, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> SubscriptionOut:
    target = _validate_target(body)
    count = (
        await session.execute(
            select(func.count()).where(NotificationSubscription.tenant_id == tenant_id)
        )
    ).scalar_one()
    if count >= MAX_SUBSCRIPTIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"at most {MAX_SUBSCRIPTIONS} subscriptions"
        )
    row = NotificationSubscription(
        tenant_id=tenant_id,
        user_id=principal.user_id,
        channel=body.channel,
        target=target,
        kinds=list(body.kinds),
        quiet_start=body.quiet_start,
        quiet_end=body.quiet_end,
        max_per_day=body.max_per_day,
        active=body.active,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "subscription already exists") from exc
    await session.refresh(row)
    return _sub_out(row)


@router.put("/subscriptions/{sub_id}", response_model=SubscriptionOut)
async def update_subscription(
    sub_id: int,
    body: SubscriptionIn,
    tenant_id: TenantDep,
    principal: PrincipalDep,
    session: SessionDep,
) -> SubscriptionOut:
    row = await _own_sub(session, tenant_id, sub_id, principal)
    row.channel = body.channel
    row.target = _validate_target(body)
    row.kinds = list(body.kinds)
    row.quiet_start, row.quiet_end = body.quiet_start, body.quiet_end
    row.max_per_day, row.active = body.max_per_day, body.active
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "subscription already exists") from exc
    await session.refresh(row)
    return _sub_out(row)


@router.delete("/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    sub_id: int, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> None:
    row = await _own_sub(session, tenant_id, sub_id, principal)
    await session.delete(row)
    await session.commit()


# ---- theo dõi lượt nhấn, "Đã xử lý" (3.6) -----------------------------------------------------


def _safe_path(to: str) -> str:
    """Chỉ chuyển hướng trong dashboard (đường dẫn tương đối): không mở chuyển hướng tuỳ ý."""
    return to if to.startswith("/") and not to.startswith("//") else "/today"


@router.get("/t/{token}", include_in_schema=False)
async def track_click(token: str, session: SessionDep, to: str = "/today") -> RedirectResponse:
    """Link trong tin (không cần đăng nhập): ghi lượt nhấn đầu tiên rồi chuyển tới trang."""
    row = (
        await session.execute(
            select(NotificationDelivery).where(NotificationDelivery.token == token)
        )
    ).scalar_one_or_none()
    if row is not None and row.clicked_at is None:
        row.clicked_at = datetime.now(tz=UTC)
        await session.commit()
    return RedirectResponse(_safe_path(to), status_code=status.HTTP_302_FOUND)


@router.get("/t/{token}/resolve", include_in_schema=False)
async def track_resolve(token: str, session: SessionDep) -> RedirectResponse:
    """Nút "Đã xử lý" trong tin: ghi nhận cho lần gửi và cho thông báo."""
    row = (
        await session.execute(
            select(NotificationDelivery).where(NotificationDelivery.token == token)
        )
    ).scalar_one_or_none()
    if row is not None:
        now = datetime.now(tz=UTC)
        row.resolved_at = row.resolved_at or now
        row.clicked_at = row.clicked_at or now
        n = await session.get(Notification, row.notification_id)
        if n is not None and n.resolved_at is None:
            n.resolved_at = now
        await session.commit()
    return RedirectResponse("/today?resolved=1", status_code=status.HTTP_302_FOUND)


@router.post("/{notification_id}/resolve", response_model=NotificationLogOut)
async def resolve_notification(
    notification_id: int, tenant_id: TenantDep, principal: PrincipalDep, session: SessionDep
) -> NotificationLogOut:
    """Đánh dấu "Đã xử lý" trên dashboard (người đang đăng nhập)."""
    row = await session.get(Notification, notification_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    row.resolved_at = row.resolved_at or datetime.now(tz=UTC)
    row.resolved_by = row.resolved_by or principal.user_id
    await session.commit()
    return _log_out(row, principal.is_operator)


@router.get("/engagement", response_model=EngagementOut)
async def engagement(
    tenant_id: TenantDep, session: SessionDep, weeks: int = Query(8, ge=1, le=52)
) -> EngagementOut:
    """Số tin gửi/lỗi/bỏ qua, lượt nhấn, "Đã xử lý" và chi phí theo tuần ISO, theo kênh (đo O4)."""
    since = datetime.now(tz=UTC) - timedelta(weeks=weeks)
    week = func.to_char(NotificationDelivery.created_at, 'IYYY-"W"IW')
    rows = await session.execute(
        select(
            week,
            NotificationDelivery.channel,
            func.count().filter(NotificationDelivery.status == "sent"),
            func.count().filter(NotificationDelivery.status == "failed"),
            func.count().filter(NotificationDelivery.status.like("skipped%")),
            func.count(NotificationDelivery.clicked_at),
            func.count(NotificationDelivery.resolved_at),
            func.coalesce(func.sum(NotificationDelivery.cost_vnd), 0),
        )
        .where(
            NotificationDelivery.tenant_id == tenant_id, NotificationDelivery.created_at >= since
        )
        .group_by(week, NotificationDelivery.channel)
        .order_by(week, NotificationDelivery.channel)
    )
    return EngagementOut(
        weeks=[
            EngagementWeekOut(
                week=w,
                channel=ch,
                sent=sent,
                failed=failed,
                skipped=skipped,
                clicked=clicked,
                resolved=resolved,
                cost_vnd=Decimal(cost),
            )
            for w, ch, sent, failed, skipped, clicked, resolved, cost in rows
        ]
    )
