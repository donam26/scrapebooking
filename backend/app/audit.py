"""Nhật ký thao tác nhạy cảm (bảng audit_events). Ghi trong cùng transaction với thao tác; không
bao giờ làm thao tác chính thất bại."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent
from app.logging import get_logger

log = get_logger(__name__)

# Hành động chuẩn (ổn định để lọc): auth.login, auth.login_failed, auth.logout_all,
# auth.password_changed, auth.password_reset_requested, auth.password_reset, user.created,
# user.updated, tenant.settings_updated, tenant.updated, watchlist.added, watchlist.updated,
# watchlist.removed, listing.added, listing.action, market_area.deleted.


def record_audit(
    session: AsyncSession,
    *,
    action: str,
    tenant_id: int | None = None,
    user_id: int | None = None,
    target: str | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    try:
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action[:48],
                target=(target or "")[:120] or None,
                payload=payload or {},
                ip=(ip or "")[:64] or None,
            )
        )
    except Exception:  # noqa: BLE001
        log.exception("audit_record_failed", action=action)
