"""Lời mời đặt mật khẩu (UX Phase 3, C5): link dùng một lần, hết hạn sau 72 giờ.

Token trong link có dạng `<user_id>.<bí mật>`; DB chỉ giữ sha256 của phần bí mật. Kiểm tra bằng
`hmac.compare_digest` (so sánh thời gian hằng) sau khi nạp người dùng theo id, nên không dò được
bí mật qua thời gian phản hồi. Mời lại thay hash mới: link cũ mất hiệu lực ngay.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UNUSABLE_PASSWORD_PREFIX, User

INVITE_TTL = timedelta(hours=72)
INVITE_TTL_HOURS = int(INVITE_TTL.total_seconds() // 3600)
_DUMMY_HASH = "0" * 64


class InviteInvalid(ValueError):
    """Token sai, đã dùng, bị thay bằng lời mời mới hoặc tài khoản đã khoá."""


class InviteExpired(ValueError):
    """Token đúng nhưng quá hạn."""


def unusable_password() -> str:
    return UNUSABLE_PASSWORD_PREFIX + secrets.token_hex(16)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue_invite(user: User, now: datetime) -> str:
    """Tạo token mới cho người dùng (cần `user.id`, tức đã flush). Trả token đầy đủ cho link."""
    secret = secrets.token_urlsafe(32)
    user.invite_token_hash = _digest(secret)
    user.invite_expires_at = now + INVITE_TTL
    return f"{user.id}.{secret}"


def invite_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/set-password?token={token}"


async def redeem_invite(session: AsyncSession, token: str, now: datetime) -> User:
    """Người dùng của token còn hiệu lực; ném `InviteInvalid` / `InviteExpired`."""
    uid, sep, secret = token.strip().partition(".")
    if not sep or not uid.isdigit() or not secret or len(uid) > 12:
        raise InviteInvalid
    user = await session.get(User, int(uid))
    stored = user.invite_token_hash if user is not None else None
    # So sánh luôn chạy (kể cả khi không có người dùng/hash) để thời gian phản hồi như nhau.
    ok = hmac.compare_digest(_digest(secret), stored or _DUMMY_HASH)
    if user is None or stored is None or not ok or not user.active:
        raise InviteInvalid
    if user.invite_expires_at is None or user.invite_expires_at <= now:
        raise InviteExpired
    return user
