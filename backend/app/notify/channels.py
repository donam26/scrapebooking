"""Kênh gửi tin ngoài email (roadmap 3.1, 3.3): Zalo ZNS và webhook chat của đội khách sạn.

Mỗi kênh nhận một `Message` trung lập (tiêu đề, tóm tắt, link sâu, link "Đã xử lý") và trả mã tin
của kênh + chi phí. Telegram không làm: bị chặn ở Việt Nam từ 21/05/2025.

**Zalo ZNS** (ZBS Template Message) — cần OA doanh nghiệp đã xác thực, tài khoản Zalo Cloud nạp
trước, template được duyệt trước; link phải nằm trong nút, không trong nội dung. Mỗi loại tin một
template (`ZALO_ZNS_TEMPLATES="alerts=…,daily_insight=…,weekly_report=…,data_stale=…,test=…"`), mọi
template dùng chung bộ tham số:

    title (≤100), summary (≤200), count, date (dd/mm/yyyy), url (nút "Xem chi tiết"),
    resolve_url (nút "Đã xử lý")

Gửi: POST https://business.openapi.zalo.me/message/template, header `access_token`, body
{phone: "849…", template_id, template_data, tracking_id}. Access token sống ~25 giờ: đặt
ZALO_APP_ID/ZALO_APP_SECRET/ZALO_REFRESH_TOKEN để tự làm mới (POST oauth.zaloapp.com/v4/oa/
access_token, grant_type=refresh_token), hoặc chỉ ZALO_ZNS_ACCESS_TOKEN khi tự xoay bên ngoài.
"""

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.logging import get_logger
from app.ops.alerts import webhook_payload

log = get_logger(__name__)

ZNS_URL = "https://business.openapi.zalo.me/message/template"
ZALO_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"

Post = Callable[[str, dict[str, Any], dict[str, str]], Awaitable[tuple[int, dict[str, Any]]]]


@dataclass(frozen=True)
class Message:
    kind: str  # alerts | daily_insight | weekly_report | data_stale | test
    subject: str
    summary: str
    count: int
    date_label: str  # dd/mm/yyyy theo giờ tenant
    url: str  # link sâu (đã gắn theo dõi lượt nhấn)
    resolve_url: str  # link "Đã xử lý"


@dataclass(frozen=True)
class SendResult:
    external_id: str | None
    cost_vnd: Decimal | None = None


class ChannelNotConfigured(RuntimeError):
    pass


class Notifier(Protocol):
    channel: str

    @property
    def configured(self) -> bool: ...

    async def send(self, target: str, message: Message, tracking_id: str) -> SendResult: ...


_PHONE_RE = re.compile(r"\D")


def normalize_vn_phone(raw: str) -> str | None:
    """ "0912 345 678", "+84 912 345 678" → "84912345678" (định dạng ZNS); sai thì None."""
    digits = _PHONE_RE.sub("", raw or "")
    if digits.startswith("0"):
        digits = "84" + digits[1:]
    if not digits.startswith("84") or not 11 <= len(digits) <= 12:
        return None
    return digits


async def _http_post(
    url: str, body: dict[str, Any], headers: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json=body, headers=headers)
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:300]}
    return r.status_code, data if isinstance(data, dict) else {"data": data}


async def _http_form(
    url: str, form: dict[str, str], headers: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, data=form, headers=headers)
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:300]}
    return r.status_code, data if isinstance(data, dict) else {"data": data}


def parse_templates(spec: str) -> dict[str, str]:
    out = {}
    for pair in (spec or "").split(","):
        k, _, v = pair.partition("=")
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


class ZaloZnsNotifier:
    channel = "zalo"

    def __init__(
        self,
        access_token: str,
        templates: dict[str, str],
        cost_vnd: Decimal = Decimal(300),
        app_id: str = "",
        app_secret: str = "",
        refresh_token: str = "",
        post: Post | None = None,
        form_post: Post | None = None,
        api_url: str = ZNS_URL,
    ) -> None:
        self._token = access_token
        self._token_expires = 0.0 if not access_token else float("inf")
        self._templates = templates
        self._cost = cost_vnd
        self._app_id, self._app_secret, self._refresh = app_id, app_secret, refresh_token
        self._post = post or _http_post
        self._form = form_post or _http_form
        self._url = api_url

    @property
    def configured(self) -> bool:
        has_token = bool(self._token) or bool(self._app_id and self._app_secret and self._refresh)
        return has_token and bool(self._templates)

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires:
            return self._token
        if not (self._app_id and self._app_secret and self._refresh):
            if self._token:
                return self._token
            raise ChannelNotConfigured("zalo access token missing")
        status, data = await self._form(
            ZALO_TOKEN_URL,
            {"app_id": self._app_id, "grant_type": "refresh_token", "refresh_token": self._refresh},
            {"secret_key": self._app_secret},
        )
        token = data.get("access_token")
        if status >= 300 or not token:
            raise RuntimeError(f"zalo token refresh failed: http {status} {data}")
        self._token = str(token)
        # Zalo trả refresh token mới mỗi lần làm mới (dùng một lần).
        self._refresh = str(data.get("refresh_token") or self._refresh)
        self._token_expires = time.monotonic() + max(60, int(data.get("expires_in", 90000)) - 600)
        return self._token

    def template_data(self, m: Message) -> dict[str, str]:
        return {
            "title": m.subject[:100],
            "summary": m.summary[:200],
            "count": str(m.count),
            "date": m.date_label,
            "url": m.url,
            "resolve_url": m.resolve_url,
        }

    async def send(self, target: str, message: Message, tracking_id: str) -> SendResult:
        template = self._templates.get(message.kind) or self._templates.get("default")
        if not template:
            raise ChannelNotConfigured(f"no ZNS template for {message.kind}")
        phone = normalize_vn_phone(target)
        if phone is None:
            raise ValueError(f"invalid phone {target!r}")
        token = await self._access_token()
        status, data = await self._post(
            self._url,
            {
                "phone": phone,
                "template_id": template,
                "template_data": self.template_data(message),
                "tracking_id": tracking_id,
            },
            {"access_token": token, "Content-Type": "application/json"},
        )
        if status >= 300 or int(data.get("error", -1)) != 0:
            raise RuntimeError(
                f"zns error http {status}: {data.get('error')} {data.get('message')}"
            )
        msg_id = (data.get("data") or {}).get("msg_id")
        return SendResult(str(msg_id) if msg_id else None, self._cost)


class WebhookNotifier:
    """Webhook chat của đội khách sạn (Slack/Google Chat/Discord/Teams): một tin gọn + link."""

    channel = "webhook"

    def __init__(self, post: Post | None = None) -> None:
        self._post = post or _http_post

    @property
    def configured(self) -> bool:
        return True

    async def send(self, target: str, message: Message, tracking_id: str) -> SendResult:
        text = f"{message.subject}\n{message.summary}\n{message.url}"
        status, _ = await self._post(target, webhook_payload(target, text), {})
        if status >= 300:
            raise RuntimeError(f"webhook http {status}")
        return SendResult(None, None)


def build_notifiers(settings: Any) -> dict[str, Notifier]:
    out: dict[str, Notifier] = {"webhook": WebhookNotifier()}
    out["zalo"] = ZaloZnsNotifier(
        access_token=getattr(settings, "zalo_zns_access_token", ""),
        templates=parse_templates(getattr(settings, "zalo_zns_templates", "")),
        cost_vnd=Decimal(str(getattr(settings, "zalo_zns_cost_vnd", 300))),
        app_id=getattr(settings, "zalo_app_id", ""),
        app_secret=getattr(settings, "zalo_app_secret", ""),
        refresh_token=getattr(settings, "zalo_refresh_token", ""),
    )
    return out
