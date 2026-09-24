from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

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


# ---- tenants (operator) ----


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(_: OperatorDep, session: SessionDep) -> list[Tenant]:
    return list((await session.execute(select(Tenant).order_by(Tenant.id))).scalars().all())


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, _: OperatorDep, session: SessionDep) -> Tenant:
    _validate_times(body.scan_times)
    _validate_times([body.insight_hour])
    tenant = Tenant(**body.model_dump(), active=True)
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
    if "scan_times" in data:
        _validate_times(data["scan_times"])
    if "insight_hour" in data:
        _validate_times([data["insight_hour"]])
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
    if "scan_times" in data:
        _validate_times(data["scan_times"])
    if "insight_hour" in data:
        _validate_times([data["insight_hour"]])
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
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    await session.commit()
    return user
