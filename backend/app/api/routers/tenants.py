from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.auth import ROLE_OPERATOR, hash_password_async
from app.api.deps import OperatorDep, PrincipalDep, SessionDep, TenantDep, WriterDep, client_ip
from app.api.quotas import LIMIT_KEYS
from app.api.schemas import (
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.audit import record_audit
from app.db.models import Tenant, User

router = APIRouter(tags=["tenants"])

MAX_SCAN_TIMES = 8  # mỗi mốc là một đợt quét toàn watchlist


def _validate_limits(limits: dict[str, int] | None) -> None:
    if limits is None:
        return
    unknown = sorted(set(limits) - set(LIMIT_KEYS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown limit keys {unknown}")
    if any(v < 0 or v > 100_000 for v in limits.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "limits must be 0..100000")


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
    if data.get("reference_channel") is not None:
        from app.channels.registry import channels

        allowed = {str(c) for c, i in channels().items() if i.collectable}
        if data["reference_channel"] not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"reference_channel must be one of {sorted(allowed)}",
            )


# ---- tenants (operator) ----


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(_: OperatorDep, session: SessionDep) -> list[Tenant]:
    return list((await session.execute(select(Tenant).order_by(Tenant.id))).scalars().all())


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate, principal: OperatorDep, request: Request, session: SessionDep
) -> Tenant:
    data = body.model_dump()
    _validate_tenant_fields(data)
    tenant = Tenant(**data, active=True)
    session.add(tenant)
    await session.flush()
    record_audit(
        session,
        action="tenant.created",
        tenant_id=tenant.id,
        user_id=principal.user_id,
        ip=client_ip(request),
    )
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
    tenant_id: int,
    body: TenantUpdate,
    principal: OperatorDep,
    request: Request,
    session: SessionDep,
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    data = body.model_dump(exclude_unset=True)
    _validate_tenant_fields(data)
    _validate_limits(data.get("limits"))
    for k, v in data.items():
        setattr(tenant, k, v)
    if data.get("active") is False:
        # Tắt tenant: mọi phiên của người dùng tenant đó mất hiệu lực ngay.
        await session.execute(
            update(User)
            .where(User.tenant_id == tenant_id)
            .values(token_version=User.token_version + 1)
        )
    record_audit(
        session,
        action="tenant.updated",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        payload={"fields": sorted(data)},
        ip=client_ip(request),
    )
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
    body: TenantUpdate,
    tenant_id: TenantDep,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    data = body.model_dump(exclude_unset=True)
    data.pop("active", None)  # tenant không tự tắt mình
    data.pop("limits", None)  # hạn mức chỉ operator đặt
    _validate_tenant_fields(data)
    for k, v in data.items():
        setattr(tenant, k, v)
    record_audit(
        session,
        action="tenant.settings_updated",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        payload={"fields": sorted(data)},
        ip=client_ip(request),
    )
    await session.commit()
    return tenant


# ---- users ----


@router.get("/users", response_model=list[UserOut])
async def list_users(principal: PrincipalDep, session: SessionDep) -> list[User]:
    stmt = select(User).order_by(User.id)
    if not principal.is_operator:
        stmt = stmt.where(User.tenant_id == principal.tenant_id)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, principal: WriterDep, request: Request, session: SessionDep
) -> User:
    if body.role == ROLE_OPERATOR:
        if not principal.is_operator:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "operator only")
        tenant_id = None
    else:
        tenant_id = body.tenant_id if principal.is_operator else principal.tenant_id
        if tenant_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tenant_id required")
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    existing = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
    user = User(
        tenant_id=tenant_id,
        email=body.email.lower(),
        password_hash=await hash_password_async(body.password),
        role=body.role,
        active=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # hai yêu cầu cùng email chạy song song
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists") from exc
    record_audit(
        session,
        action="user.created",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target=f"user:{user.id}",
        payload={"role": body.role},
        ip=client_ip(request),
    )
    await session.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    principal: WriterDep,
    request: Request,
    session: SessionDep,
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
    revoke = False
    if "password" in data:
        user.password_hash = await hash_password_async(data.pop("password"))
        revoke = True
    if data.get("active") is False or ("role" in data and data["role"] != user.role):
        revoke = True  # khoá hoặc đổi vai trò: phiên đang đăng nhập mất hiệu lực ngay
    for k, v in data.items():
        setattr(user, k, v)
    if revoke:
        user.token_version = int(user.token_version or 0) + 1
    record_audit(
        session,
        action="user.updated",
        tenant_id=user.tenant_id,
        user_id=principal.user_id,
        target=f"user:{user.id}",
        payload={"fields": sorted(data) + (["password"] if revoke else [])},
        ip=client_ip(request),
    )
    await session.commit()
    return user
