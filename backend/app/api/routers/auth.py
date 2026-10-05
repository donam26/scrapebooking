"""Đăng nhập/đăng xuất, đổi và đặt lại mật khẩu.

Bảo vệ: giới hạn số lần thử theo IP và theo email (Redis khi có), xác minh giả khi email không
tồn tại (chống dò email theo thời gian), argon2 chạy trong thread, JWT mang `tv` (token_version)
để thu hồi phiên ngay khi đổi mật khẩu/"đăng xuất mọi thiết bị"."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select, update

from app.api.auth import (
    COOKIE_NAME,
    Principal,
    hash_password_async,
    issue_token,
    verify_password_async,
)
from app.api.deps import LocaleDep, PrincipalDep, SessionDep, SettingsDep, client_ip
from app.api.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    UserOut,
)
from app.api.throttle import WindowThrottle
from app.audit import record_audit
from app.config import Settings
from app.db.models import PasswordResetToken, Tenant, User
from app.i18n import t
from app.logging import get_logger
from app.notify.render import Email

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _redis(request: Request) -> Any | None:
    return getattr(getattr(request.app.state, "queue", None), "redis", None)


def _throttles(request: Request, settings: Settings) -> dict[str, WindowThrottle]:
    """Một bộ throttle cho cả tiến trình (bộ nhớ khi không có Redis)."""
    existing: dict[str, WindowThrottle] | None = getattr(request.app.state, "auth_throttles", None)
    if existing is None:
        existing = {
            "ip": WindowThrottle(settings.login_per_minute_per_ip, 60, "login_ip"),
            "email": WindowThrottle(settings.login_per_minute_per_email, 60, "login_email"),
            "email_hour": WindowThrottle(settings.login_per_hour_per_email, 3600, "login_email_h"),
            "forgot": WindowThrottle(5, 60, "forgot_ip"),
        }
        request.app.state.auth_throttles = existing
    return existing


async def _check_login_rate(request: Request, settings: Settings, email: str) -> None:
    throttles = _throttles(request, settings)
    redis = _redis(request)
    ip = client_ip(request)
    allowed = await throttles["ip"].hit(ip, redis)
    allowed = await throttles["email"].hit(email, redis) and allowed
    allowed = await throttles["email_hour"].hit(email, redis) and allowed
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many login attempts, retry later",
            headers={"Retry-After": "60"},
        )


def _set_session_cookie(response: Response, settings: Settings, principal: Principal) -> None:
    ttl = timedelta(hours=settings.jwt_ttl_hours)
    response.set_cookie(
        COOKIE_NAME,
        issue_token(principal, settings.jwt_secret, ttl),
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _principal(user: User) -> Principal:
    return Principal(user.id, user.email, user.role, user.tenant_id, int(user.token_version or 0))


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    email = body.email.lower()
    await _check_login_rate(request, settings, email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = await verify_password_async(
        body.password, user.password_hash if user is not None and user.active else None
    )
    if user is None or not user.active or not ok:
        record_audit(session, action="auth.login_failed", target=email[:120], ip=client_ip(request))
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if user.tenant_id is not None:
        tenant_active = (
            await session.execute(select(Tenant.active).where(Tenant.id == user.tenant_id))
        ).scalar_one_or_none()
        if tenant_active is False:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant disabled")
    _set_session_cookie(response, settings, _principal(user))
    record_audit(
        session,
        action="auth.login",
        tenant_id=user.tenant_id,
        user_id=user.id,
        ip=client_ip(request),
    )
    await session.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    principal: PrincipalDep, request: Request, response: Response, session: SessionDep
) -> None:
    """Thu hồi mọi phiên của chính mình (mọi thiết bị): tăng token_version."""
    await session.execute(
        update(User)
        .where(User.id == principal.user_id)
        .values(token_version=User.token_version + 1)
    )
    record_audit(
        session,
        action="auth.logout_all",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        ip=client_ip(request),
    )
    await session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
async def me(principal: PrincipalDep, session: SessionDep) -> User:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled")
    return user


@router.post("/change-password", response_model=UserOut)
async def change_password(
    body: ChangePasswordRequest,
    principal: PrincipalDep,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    """Tự đổi mật khẩu: cần mật khẩu hiện tại; phiên khác bị thu hồi, phiên này được cấp lại."""
    user = (await session.execute(select(User).where(User.id == principal.user_id))).scalar_one()
    if not await verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "current password is wrong")
    user.password_hash = await hash_password_async(body.new_password)
    user.token_version = int(user.token_version or 0) + 1
    record_audit(
        session,
        action="auth.password_changed",
        tenant_id=user.tenant_id,
        user_id=user.id,
        ip=client_ip(request),
    )
    await session.commit()
    _set_session_cookie(response, settings, _principal(user))
    return user


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reset_email(locale: str, link: str, minutes: int) -> Email:
    subject = t(locale, "auth.reset.subject")
    text = t(locale, "auth.reset.body", link=link, minutes=minutes)
    html = (
        "<p>"
        + t(locale, "auth.reset.body_html", minutes=minutes)
        + f'</p><p><a href="{link}">{link}</a></p>'
    )
    return Email(subject=subject, text=text, html=html)


@router.post("/forgot", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    locale: LocaleDep,
) -> None:
    """Luôn trả 204 (không lộ email có tồn tại hay không). Có tài khoản thì gửi link một lần."""
    throttles = _throttles(request, settings)
    if not await throttles["forgot"].hit(client_ip(request), _redis(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many requests, retry later",
            headers={"Retry-After": "60"},
        )
    email = body.email.lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    record_audit(
        session, action="auth.password_reset_requested", target=email[:120], ip=client_ip(request)
    )
    if user is None or not user.active:
        await session.commit()
        return
    token = secrets.token_urlsafe(32)
    now = datetime.now(tz=UTC)
    session.add(
        PasswordResetToken(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    await session.commit()
    from app.api.routers.notifications import get_email_sender

    sender = get_email_sender(request, settings)
    if not sender.configured:
        log.warning("password_reset_email_not_configured", user_id=user.id)
        return
    link = f"{settings.app_base_url.rstrip('/')}/reset?token={token}"
    try:
        await sender.send(
            user.email, _reset_email(locale, link, settings.password_reset_ttl_minutes)
        )
    except Exception:  # noqa: BLE001 — không lộ lỗi SMTP cho người gọi
        log.exception("password_reset_email_failed", user_id=user.id)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordRequest, request: Request, session: SessionDep) -> None:
    now = datetime.now(tz=UTC)
    row = (
        await session.execute(
            select(PasswordResetToken, User)
            .join(User, User.id == PasswordResetToken.user_id)
            .where(PasswordResetToken.token_hash == _token_hash(body.token))
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired token")
    reset, user = row[0], row[1]
    if reset.used_at is not None or reset.expires_at < now or not user.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired token")
    user.password_hash = await hash_password_async(body.password)
    user.token_version = int(user.token_version or 0) + 1
    reset.used_at = now
    record_audit(
        session,
        action="auth.password_reset",
        tenant_id=user.tenant_id,
        user_id=user.id,
        ip=client_ip(request),
    )
    await session.commit()
