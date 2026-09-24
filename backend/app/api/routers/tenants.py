from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.auth import ROLE_OPERATOR, hash_password
from app.api.deps import OperatorDep, PrincipalDep, SessionDep, TenantDep, WriterDep
from app.api.schemas import (
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.db.models import Tenant, User

router = APIRouter(tags=["tenants"])


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
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown timezone {tz!r} (múi giờ không hợp lệ)"
        ) from exc


def _validate_tenant_fields(data: dict) -> None:  # type: ignore[type-arg]
    if "scan_times" in data:
        if not data["scan_times"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "scan_times must not be empty"
            )
        _validate_times(data["scan_times"])
        data["scan_times"] = sorted(set(data["scan_times"]))
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


# ---- users ----


@router.get("/users", response_model=list[UserOut])
async def list_users(principal: PrincipalDep, session: SessionDep) -> list[User]:
    stmt = select(User).order_by(User.id)
    if not principal.is_operator:
        stmt = stmt.where(User.tenant_id == principal.tenant_id)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, principal: WriterDep, session: SessionDep) -> User:
    if body.role == ROLE_OPERATOR:
        if not principal.is_operator:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "operator only")
        tenant_id = None
    else:
        tenant_id = body.tenant_id if principal.is_operator else principal.tenant_id
        if tenant_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tenant_id required")
    existing = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
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
    for k, v in data.items():
        setattr(user, k, v)
    await session.commit()
    return user
