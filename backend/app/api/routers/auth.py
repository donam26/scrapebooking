from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.auth import COOKIE_NAME, Principal, issue_token, verify_password
from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas import LoginRequest, UserOut
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> User:
    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    principal = Principal(user.id, user.email, user.role, user.tenant_id)
    ttl = timedelta(hours=settings.jwt_ttl_hours)
    token = issue_token(principal, settings.jwt_secret, ttl)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
async def me(principal: PrincipalDep, session: SessionDep) -> User:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled")
    return user
