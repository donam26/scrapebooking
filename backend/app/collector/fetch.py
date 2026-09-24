import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.collector.session import ScrapeSession


class FetchOutcome(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"


BLOCK_MARKERS = (
    "awswaf",
    "aws-waf",
    "challenge.js",
    "captcha-delivery",
    "pardon our interruption",
    "verify you are a human",
    "access denied",
)


def classify_response(status: int, text: str) -> FetchOutcome:
    if status in (403, 429, 503, 202):
        return FetchOutcome.BLOCKED
    if status == 404:
        return FetchOutcome.NOT_FOUND
    head = text[:20_000].lower()
    if any(marker in head for marker in BLOCK_MARKERS):
        return FetchOutcome.BLOCKED
    if status >= 400:
        return FetchOutcome.ERROR
    return FetchOutcome.OK


@dataclass(frozen=True)
class FetchResponse:
    status: int
    text: str
    url: str
    elapsed_ms: int

    @property
    def outcome(self) -> FetchOutcome:
        return classify_response(self.status, self.text)


class Fetcher(Protocol):
    async def get(self, url: str, session: ScrapeSession) -> FetchResponse: ...
    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse: ...
    async def close(self, session_id: str) -> None: ...


class CurlFetcher:
    """HTTP client giả lập TLS fingerprint Chrome, dùng cookie và proxy của ScrapeSession.
    Một AsyncSession curl_cffi cho mỗi ScrapeSession, đóng khi session bị thu hồi."""

    def __init__(self, timeout_s: float = 30.0, impersonate: str = "chrome") -> None:
        self._timeout = timeout_s
        self._impersonate = impersonate
        self._clients: dict[str, Any] = {}

    def _client(self, session: ScrapeSession) -> Any:
        client = self._clients.get(session.id)
        if client is None:
            from curl_cffi.requests import AsyncSession

            client = AsyncSession(
                impersonate=self._impersonate,
                proxies={"http": session.proxy.url, "https": session.proxy.url},
                timeout=self._timeout,
            )
            self._clients[session.id] = client
        return client

    @staticmethod
    def _base_headers(session: ScrapeSession) -> dict[str, str]:
        return {
            "User-Agent": session.user_agent,
            "Accept-Language": "en-GB,en;q=0.9",
        }

    async def get(self, url: str, session: ScrapeSession) -> FetchResponse:
        headers = self._base_headers(session) | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }
        t0 = time.monotonic()
        r = await self._client(session).get(url, headers=headers, cookies=session.cookies)
        return FetchResponse(
            status=r.status_code,
            text=r.text,
            url=str(r.url),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse:
        merged = self._base_headers(session) | {"Content-Type": "application/json"} | headers
        t0 = time.monotonic()
        r = await self._client(session).post(
            url, json=payload, headers=merged, cookies=session.cookies
        )
        return FetchResponse(
            status=r.status_code,
            text=r.text,
            url=str(r.url),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    async def close(self, session_id: str) -> None:
        client = self._clients.pop(session_id, None)
        if client is not None:
            await client.close()

    async def close_all(self) -> None:
        for sid in list(self._clients):
            await self.close(sid)
