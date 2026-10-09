"""Kiểm tra proxy: gọi một dịch vụ trả IP qua từng proxy. Dùng ở scheduler (định kỳ và trước mỗi
mốc quét) và CLI. Kết quả được chia sẻ cho worker qua Redis (`ProxyHealthStore`) để worker bỏ qua
template đang hỏng thay vì xoay vòng mù (roadmap 0.2)."""

import json
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.collector.proxy import template_label

CHECK_URL = "https://api.ipify.org?format=json"
HEALTH_KEY = "proxy:health"
HEALTH_TTL_SECONDS = 3600  # kết quả cũ hơn 1 giờ (scheduler chết) thì không dùng nữa


@dataclass(frozen=True)
class ProxyHealth:
    proxy: str  # nhãn template "#1 host:port", không có mật khẩu
    ok: bool
    exit_ip: str | None
    elapsed_ms: int
    error: str | None = None


async def check_proxy(
    template: str, country: str = "vn", timeout_s: float = 20.0, index: int = 0
) -> ProxyHealth:
    url = template.format(country=country, session=secrets.token_hex(4))
    label = template_label(template, index)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(proxy=url, timeout=timeout_s) as client:
            r = await client.get(CHECK_URL)
        elapsed = int((time.monotonic() - t0) * 1000)
        if r.status_code != 200:
            return ProxyHealth(label, False, None, elapsed, f"http {r.status_code}")
        return ProxyHealth(label, True, r.json().get("ip"), elapsed)
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.monotonic() - t0) * 1000)
        return ProxyHealth(label, False, None, elapsed, f"{type(exc).__name__}: {exc}"[:300])


async def check_proxies(templates: list[str], country: str = "vn") -> list[ProxyHealth]:
    return [await check_proxy(t, country, index=i) for i, t in enumerate(templates)]


def all_down(results: list[ProxyHealth]) -> bool:
    return bool(results) and not any(r.ok for r in results)


def proxy_alert(results: list[ProxyHealth]) -> str | None:
    bad = [r for r in results if not r.ok]
    if not bad:
        return None
    lines = [f"- {r.proxy}: {r.error}" for r in bad]
    head = "⚠️ All proxies failing" if len(bad) == len(results) else "⚠️ Some proxies failing"
    tail = (
        "; scans are deferred until a proxy works"
        if len(bad) == len(results)
        else "; scans use the healthy providers"
    )
    return head + f" ({len(bad)}/{len(results)}){tail}\n" + "\n".join(lines)


class _Redis(Protocol):
    async def hset(self, name: str, mapping: dict[str, str]) -> Any: ...
    async def hgetall(self, name: str) -> dict[Any, Any]: ...
    async def expire(self, name: str, time: int) -> Any: ...
    async def delete(self, *names: str) -> Any: ...


class ProxyHealthStore:
    """Kết quả kiểm tra proxy gần nhất trong Redis (hash `proxy:health`, nhãn → JSON)."""

    def __init__(self, redis: "_Redis | Any") -> None:
        self._r = redis

    async def write(self, results: Iterable[ProxyHealth], now: datetime | None = None) -> None:
        at = (now or datetime.now(tz=UTC)).isoformat()
        mapping = {
            r.proxy: json.dumps({"ok": r.ok, "error": r.error, "checked_at": at}) for r in results
        }
        if not mapping:
            return
        await self._r.delete(HEALTH_KEY)
        await self._r.hset(HEALTH_KEY, mapping=mapping)
        await self._r.expire(HEALTH_KEY, HEALTH_TTL_SECONDS)

    async def read(self) -> dict[str, dict[str, Any]]:
        raw = await self._r.hgetall(HEALTH_KEY)
        out: dict[str, dict[str, Any]] = {}
        for k, v in raw.items():
            key = k.decode() if isinstance(k, bytes) else str(k)
            try:
                out[key] = json.loads(v.decode() if isinstance(v, bytes) else v)
            except (ValueError, AttributeError):
                continue
        return out

    async def down_labels(self) -> set[str]:
        return {label for label, v in (await self.read()).items() if not v.get("ok")}
