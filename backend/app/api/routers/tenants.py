from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.auth import ROLE_OPERATOR, Principal, hash_password
from app.api.deps import (
    OperatorDep,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TenantDep,
    WriterDep,
)
from app.api.invites import (
    INVITE_TTL_HOURS,
    invite_url,
    issue_invite,
    unusable_password,
)
from app.api.routers.notifications import SenderDep
from app.api.schemas import (
    InviteOut,
    SetupOut,
    SetupUpdate,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserInvite,
    UserOut,
    UserUpdate,
)
from app.api.setup_state import build_setup
from app.config import Settings
from app.db.models import Tenant, User
from app.i18n import normalize_locale
from app.logging import get_logger
from app.notify.email_sender import EmailSender
from app.notify.render import render_invite

router = APIRouter(tags=["tenants"])
log = get_logger(__name__)

MAX_SCAN_TIMES = 8  # mỗi mốc là một đợt quét toàn watchlist


def _validate_times(times: list[str]) -> None:
    for t in times:
        try:
            hh, mm = t.split(":")
            assert 0 <= int(hh) < 24 and 0 <= int(mm) < 60
        except (ValueError, AssertionError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bad time {t!r}") from exc


def _validate_timezone(tz: str) -> None:
    """Múi giờ sai sẽ làm scheduler ném lỗi ở mọi tick: chặn ngay ở API."""
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown timezone {tz!r}"
        ) from exc


def _validate_tenant_fields(data: dict) -> None:  # type: ignore[type-arg]
    if "scan_times" in data:
        if not data["scan_times"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "scan_times must not be empty"
            )
        _validate_times(data["scan_times"])
        data["scan_times"] = sorted(set(data["scan_times"]))
        if len(data["scan_times"]) > MAX_SCAN_TIMES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"at most {MAX_SCAN_TIMES} scan_times per day",
            )
    if "insight_hour" in data:
        _validate_times([data["insight_hour"]])
    if "timezone" in data:
        _validate_timezone(data["timezone"])
    if "country_code" in data:
        data["country_code"] = data["country_code"].lower()


# ---- tenants (operator) ----


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(_: OperatorDep, session: SessionDep) -> list[Tenant]:
    return list((await session.execute(select(Tenant).order_by(Tenant.id))).scalars().all())


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, _: OperatorDep, session: SessionDep) -> Tenant:
    data = body.model_dump()
    _validate_tenant_fields(data)
    tenant = Tenant(**data, active=True)
    session.add(tenant)
    await session.commit()
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: int, _: OperatorDep, session: SessionDep) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: int, body: TenantUpdate, _: OperatorDep, session: SessionDep
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    data = body.model_dump(exclude_unset=True)
    _validate_tenant_fields(data)
    for k, v in data.items():
        setattr(tenant, k, v)
    await session.commit()
    return tenant


# ---- tenant settings (tenant_admin sửa tenant của mình) ----


@router.get("/settings", response_model=TenantOut)
async def get_settings_(tenant_id: TenantDep, session: SessionDep) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return tenant


@router.patch("/settings", response_model=TenantOut)
async def update_settings(
    body: TenantUpdate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    data = body.model_dump(exclude_unset=True)
    data.pop("active", None)  # tenant không tự tắt mình
    _validate_tenant_fields(data)
    for k, v in data.items():
        setattr(tenant, k, v)
    await session.commit()
    return tenant


@router.get("/settings/setup", response_model=SetupOut)
async def get_setup(tenant_id: TenantDep, session: SessionDep) -> SetupOut:
    """Thẻ "Thiết lập 5 bước" trên Hôm nay: bước nào đã xong, đã ẩn chưa, nhóm đối thủ có cân về
    giá không (Q4)."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return await build_setup(session, tenant)


@router.put("/settings/setup", response_model=SetupOut)
async def update_setup(
    body: SetupUpdate, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> SetupOut:
    """ "Ẩn" thẻ thiết lập (lưu ở tenant, mọi người dùng của tenant cùng thấy) hoặc hiện lại."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    state = dict(tenant.setup_state or {})
    if body.dismissed:
        state["dismissed_at"] = datetime.now(tz=UTC).isoformat()
    else:
        state.pop("dismissed_at", None)
    tenant.setup_state = state
    await session.commit()
    return await build_setup(session, tenant)


# ---- users ----


@router.get("/users", response_model=list[UserOut])
async def list_users(principal: PrincipalDep, session: SessionDep) -> list[User]:
    stmt = select(User).order_by(User.id)
    if not principal.is_operator:
        stmt = stmt.where(User.tenant_id == principal.tenant_id)
    return list((await session.execute(stmt)).scalars().all())


def _new_user_tenant(role: str, tenant_id: int | None, principal: Principal) -> int | None:
    """Tenant của tài khoản mới: operator không thuộc tenant; tenant_admin chỉ thêm vào tenant
    của mình."""
    if role == ROLE_OPERATOR:
        if not principal.is_operator:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "operator only")
        return None
    tid = tenant_id if principal.is_operator else principal.tenant_id
    if tid is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tenant_id required")
    return tid


async def _ensure_email_free(session: SessionDep, email: str) -> None:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, principal: WriterDep, session: SessionDep) -> User:
    tenant_id = _new_user_tenant(body.role, body.tenant_id, principal)
    await _ensure_email_free(session, body.email.lower())
    user = User(
        tenant_id=tenant_id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
        active=True,
    )
    session.add(user)
    await session.commit()
    return user


async def _send_invite(
    session: SessionDep, user: User, sender: EmailSender, settings: Settings
) -> InviteOut:
    """Token mới (link cũ mất hiệu lực), lưu, rồi gửi email nếu đơn vị vận hành đã bật SMTP.
    Link luôn trả về để quản trị tự gửi khi email chưa đi được."""
    now = datetime.now(tz=UTC)
    await session.flush()
    url = invite_url(settings.app_base_url, issue_invite(user, now))
    await session.commit()
    assert user.invite_expires_at is not None
    email_status: Literal["sent", "not_configured", "failed"] = "not_configured"
    if sender.configured:
        tenant = await session.get(Tenant, user.tenant_id) if user.tenant_id else None
        email = render_invite(
            tenant.name if tenant else "OTARadar",
            user.email,
            user.role,
            url,
            INVITE_TTL_HOURS,
            normalize_locale(tenant.insight_language if tenant else None),
        )
        try:
            await sender.send(user.email, email)
            email_status = "sent"
        except Exception as exc:  # noqa: BLE001  (SMTP từ chối/không tới được)
            log.warning("invite_email_failed", user_id=user.id, error=str(exc))
            email_status = "failed"
    return InviteOut(
        user=UserOut.model_validate(user),
        invite_url=url,
        expires_at=user.invite_expires_at,
        email_status=email_status,
    )


@router.post("/users/invite", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserInvite,
    principal: WriterDep,
    session: SessionDep,
    sender: SenderDep,
    settings: SettingsDep,
) -> InviteOut:
    """Thêm người bằng lời mời: tài khoản có mật khẩu không dùng được cho tới khi họ tự đặt."""
    tenant_id = _new_user_tenant(body.role, body.tenant_id, principal)
    await _ensure_email_free(session, body.email.lower())
    user = User(
        tenant_id=tenant_id,
        email=body.email.lower(),
        password_hash=unusable_password(),
        role=body.role,
        active=True,
    )
    session.add(user)
    return await _send_invite(session, user, sender, settings)


@router.post("/users/{user_id}/invite", response_model=InviteOut)
async def resend_invite(
    user_id: int,
    principal: WriterDep,
    session: SessionDep,
    sender: SenderDep,
    settings: SettingsDep,
) -> InviteOut:
    """Gửi lại lời mời cho người chưa đặt mật khẩu; link trước đó hết hiệu lực."""
    user = await session.get(User, user_id)
    if user is None or (not principal.is_operator and user.tenant_id != principal.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if not user.invite_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "user already has a password")
    if not user.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "user disabled")
    return await _send_invite(session, user, sender, settings)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdate, principal: WriterDep, session: SessionDep
) -> User:
    user = await session.get(User, user_id)
    if user is None or (not principal.is_operator and user.tenant_id != principal.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("role") == ROLE_OPERATOR and not principal.is_operator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator only")
    if user.id == principal.user_id and (
        data.get("active") is False or ("role" in data and data["role"] != user.role)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cannot lock or change the role of your own account",
        )
    if user.role == ROLE_OPERATOR and (
        data.get("active") is False or data.get("role") not in (None, ROLE_OPERATOR)
    ):
        others = await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == ROLE_OPERATOR, User.active.is_(True), User.id != user.id)
        )
        if others.scalar_one() == 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "cannot remove the last active operator"
            )
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
        # Quản trị đặt mật khẩu thay: link mời đang treo (nếu có) không dùng được nữa.
        user.invite_token_hash = None
        user.invite_expires_at = None
    for k, v in data.items():
        setattr(user, k, v)
    await session.commit()
    return user
