"""Lưu HTML thật của trang khách sạn Booking làm fixture (rút gọn + gzip).

Tải giống worker: Playwright lấy cookie qua challenge, rồi curl_cffi tải trang có ngày. Chỉ giữ các
phần parser đọc (script có b_hotel_id/b_csrf_token, tiêu đề, ô checkin, thông báo hết phòng, bảng
#hprt-table) để fixture nhỏ mà vẫn là markup thật.

Dùng:
  uv run python scripts/capture_fixture.py <booking_hotel_url> <checkin YYYY-MM-DD> <nights> <tên_fixture>
  uv run python scripts/capture_fixture.py --from-file <trang.html> <tên_fixture>   # rút gọn trang đã lưu
Ví dụ: uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-10-10 1 reverie_2026-10-10
"""

import asyncio
import gzip
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from selectolax.parser import HTMLParser

from app.collector.booking import selectors as S

OUT = Path(__file__).parent.parent / "tests" / "fixtures" / "html"

_JS_VARS = re.compile(r"^\s*(b_hotel_id|b_hotel_name|b_csrf_token)\s*:.*$", re.M)


def trim_hotel_page(html: str) -> str:
    tree = HTMLParser(html)
    js = "\n".join(m.group(0).strip() for m in _JS_VARS.finditer(html))
    js = re.sub(r"(b_csrf_token\s*:\s*')[^']*'", r"\1FIXTURE_CSRF_TOKEN'", js)  # token phiên thật
    parts: list[str] = []
    for selector in (S.HOTEL_NAME, "input[name='checkin']", S.SOLD_OUT_MARKERS, S.ROOM_TABLE):
        for node in tree.css(selector):
            if node.html and node.html not in parts:
                parts.append(node.html)
    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n"
        f"<script>\nvar booking = {{env: {{\n{js}\n}}}};\n</script>\n</head>\n<body>\n{body}\n</body></html>\n"
    )


def write_fixture(html: str, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.html.gz"
    trimmed = trim_hotel_page(html)
    path.write_bytes(gzip.compress(trimmed.encode("utf-8"), mtime=0))
    print(f"saved {path} ({len(html)} -> {len(trimmed)} bytes, gz {path.stat().st_size})")
    return path


async def capture(url: str, checkin: str, nights: str, name: str) -> None:
    from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
    from app.collector.booking.urls import build_hotel_url, currency_for
    from app.collector.fetch import CurlFetcher
    from app.collector.proxy import StaticProxyProvider
    from app.collector.session import ScrapeSession
    from app.config import get_settings
    from app.domain.booking_url import parse_booking_url
    from app.domain.models import HotelRef

    s = get_settings()
    ref = parse_booking_url(url)
    hotel = HotelRef(
        id=0, country_code=ref.country_code, slug=ref.slug, canonical_url=ref.canonical_url
    )
    target = build_hotel_url(
        hotel,
        date.fromisoformat(checkin),
        int(nights),
        s.default_adults,
        currency_for(ref.country_code),
    )
    proxy = StaticProxyProvider(s.proxy_url_template).new_endpoint(ref.country_code)
    boot = await PlaywrightBootstrapper(headless=s.playwright_headless).bootstrap(
        proxy, ref.canonical_url
    )
    session = ScrapeSession(
        uuid.uuid4().hex[:16],
        proxy,
        boot.cookies,
        boot.user_agent,
        boot.csrf_token,
        datetime.now(tz=UTC),
    )
    fetcher = CurlFetcher()
    try:
        r = await fetcher.get(target, session)
    finally:
        await fetcher.close_all()
    print(f"GET {target} -> http {r.status}, {len(r.text)} bytes")
    write_fixture(r.text, name)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--from-file":
        write_fixture(Path(sys.argv[2]).read_text(encoding="utf-8"), sys.argv[3])
    else:
        asyncio.run(capture(*sys.argv[1:5]))
