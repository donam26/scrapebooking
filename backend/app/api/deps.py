from collections.abc import AsyncIterator
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, InvalidToken, Principal, decode_token
from app.config import Settings, get_settings
from app.db.models import TenantHotel


class ApiQueue(Protocol):
    async def enqueue_insight(self, tenant_id: int, trigger: str, request_key: str) -> None: ...
    async def enqueue_analytics(self, scan_run_id: int) -> None: ...


def get_app_settings(request: Request) -> Settings:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings or get_settings()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_queue(request: Request) -> ApiQueue | None:
    queue: ApiQueue | None = getattr(request.app.state, "queue", None)
    return queue


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_principal(request: Request, settings: SettingsDep) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        return decode_token(token, settings.jwt_secret)
    except InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session") from exc


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_operator(principal: PrincipalDep) -> Principal:
    if not principal.is_operator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator only")
    return principal


def require_write(principal: PrincipalDep) -> Principal:
    if not principal.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "read-only role")
    return principal


OperatorDep = Annotated[Principal, Depends(require_operator)]
WriterDep = Annotated[Principal, Depends(require_write)]


def current_tenant_id(
    principal: PrincipalDep,
    tenant_id: Annotated[int | None, Query(description="Operator: tenant cần xem")] = None,
) -> int:
    """Tenant của request: operator phải chỉ định ?tenant_id=, người dùng tenant lấy từ token."""
    if principal.is_operator:
        if tenant_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant_id is required for operator")
        return tenant_id
    if principal.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user has no tenant")
    if tenant_id is not None and tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cannot access another tenant")
    return principal.tenant_id


TenantDep = Annotated[int, Depends(current_tenant_id)]


async def tenant_hotel_ids(
    session: AsyncSession, tenant_id: int, include_inactive: bool = False
) -> list[int]:
    stmt = select(TenantHotel.hotel_id).where(TenantHotel.tenant_id == tenant_id)
    if not include_inactive:
        stmt = stmt.where(TenantHotel.active.is_(True))
    return [r[0] for r in await session.execute(stmt)]


async def ensure_hotel_in_tenant(session: AsyncSession, tenant_id: int, hotel_id: int) -> None:
    ids = await tenant_hotel_ids(session, tenant_id, include_inactive=True)
    if hotel_id not in ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hotel not in watchlist")
