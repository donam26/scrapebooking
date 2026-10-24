from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.auth import COOKIE_NAME, Principal, hash_password, issue_token, verify_password
from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.invites import InviteExpired, InviteInvalid, redeem_invite
from app.api.schemas import LoginRequest, SetPasswordRequest, UserOut
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> User:
    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    # Người được mời chưa đặt mật khẩu có hash không dùng được: verify_password luôn sai.
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    user.last_login_at = datetime.now(tz=UTC)
    await session.commit()
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


@router.post("/set-password", status_code=status.HTTP_204_NO_CONTENT)
async def set_password(body: SetPasswordRequest, session: SessionDep) -> None:
    """Công khai: người được mời đặt mật khẩu bằng token trong link (dùng một lần, 72 giờ).
    Không tự đăng nhập; trang /set-password chuyển về /login."""
    try:
        user = await redeem_invite(session, body.token, datetime.now(tz=UTC))
    except InviteExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, "invite token expired") from exc
    except InviteInvalid as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid invite token") from exc
    user.password_hash = hash_password(body.password)
    user.invite_token_hash = None
    user.invite_expires_at = None
    await session.commit()


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
