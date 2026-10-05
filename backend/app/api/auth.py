import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

ROLE_OPERATOR = "operator"
ROLE_TENANT_ADMIN = "tenant_admin"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_OPERATOR, ROLE_TENANT_ADMIN, ROLE_VIEWER)
COOKIE_NAME = "sb_session"
# Băm cố định để xác minh "giả" khi email không tồn tại: thời gian trả lời như tài khoản thật
# (chống dò email theo thời gian).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001  (hash lỗi định dạng)
        return False


async def hash_password_async(password: str) -> str:
    """argon2 tốn ~50 ms CPU và 64 MiB: chạy trong thread để không chặn event loop API."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    """`password_hash=None` (email không tồn tại): vẫn chạy một lần băm giả rồi trả False."""
    if password_hash is None:
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        return False
    return await asyncio.to_thread(verify_password, password, password_hash)


@dataclass(frozen=True)
class Principal:
    user_id: int
    email: str
    role: str
    tenant_id: int | None
    token_version: int = 0

    @property
    def is_operator(self) -> bool:
        return self.role == ROLE_OPERATOR

    @property
    def can_write(self) -> bool:
        return self.role in (ROLE_OPERATOR, ROLE_TENANT_ADMIN)


def issue_token(
    principal: Principal, secret: str, ttl: timedelta, now: datetime | None = None
) -> str:
    now = now or datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": str(principal.user_id),
        "email": principal.email,
        "role": principal.role,
        "tenant_id": principal.tenant_id,
        "tv": principal.token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class InvalidToken(ValueError):
    pass


def decode_token(token: str, secret: str) -> Principal:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    return Principal(
        user_id=int(payload["sub"]),
        email=str(payload.get("email", "")),
        role=str(payload["role"]),
        tenant_id=payload.get("tenant_id"),
        token_version=int(payload.get("tv", 0)),
    )
