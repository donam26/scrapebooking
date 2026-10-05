"""Kiểm tra proxy: gọi một dịch vụ trả IP qua từng proxy. Dùng ở scheduler (định kỳ) và CLI."""

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

CHECK_URL = "https://api.ipify.org?format=json"


@dataclass(frozen=True)
class ProxyHealth:
    proxy: str  # host:port, không có mật khẩu
    ok: bool
    exit_ip: str | None
    elapsed_ms: int
    error: str | None = None


def _label(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else str(parsed.hostname)


async def check_proxy(template: str, country: str = "vn", timeout_s: float = 20.0) -> ProxyHealth:
    url = template.format(country=country, session=secrets.token_hex(4))
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(proxy=url, timeout=timeout_s) as client:
            r = await client.get(CHECK_URL)
        elapsed = int((time.monotonic() - t0) * 1000)
        if r.status_code != 200:
            return ProxyHealth(_label(url), False, None, elapsed, f"http {r.status_code}")
        return ProxyHealth(_label(url), True, r.json().get("ip"), elapsed)
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.monotonic() - t0) * 1000)
        return ProxyHealth(_label(url), False, None, elapsed, f"{type(exc).__name__}: {exc}")


async def check_proxies(templates: list[str], country: str = "vn") -> list[ProxyHealth]:
    return [await check_proxy(t, country) for t in templates]


def proxy_alert(results: list[ProxyHealth]) -> str | None:
    bad = [r for r in results if not r.ok]
    if not bad:
        return None
    lines = [f"- {r.proxy}: {r.error}" for r in bad]
    head = "⚠️ All proxies failing" if len(bad) == len(results) else "⚠️ Some proxies failing"
    return head + f" ({len(bad)}/{len(results)}); scans will fail until fixed\n" + "\n".join(lines)
