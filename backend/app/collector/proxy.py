import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProxyEndpoint:
    server: str  # scheme://host:port, không kèm thông tin đăng nhập
    username: str | None
    password: str | None
    country: str
    session_id: str
    url: str  # URL đầy đủ cho HTTP client

    @property
    def id(self) -> str:
        return f"{self.country}:{self.session_id}"


class ProxyProvider(Protocol):
    def new_endpoint(self, country: str) -> ProxyEndpoint: ...


class StaticProxyProvider:
    """Sinh endpoint từ template có {country} và {session}.

    Ví dụ: http://USER-country-{country}-session-{session}:PASS@gate.provider.com:7777
    Mỗi lần gọi new_endpoint tạo session id mới, nghĩa là IP residential mới (sticky).
    """

    def __init__(
        self, template: str, id_factory: Callable[[], str] = lambda: secrets.token_hex(4)
    ) -> None:
        self._template = template
        self._id_factory = id_factory

    def new_endpoint(self, country: str) -> ProxyEndpoint:
        session_id = self._id_factory()
        url = self._template.format(country=country, session=session_id)
        parsed = urlparse(url)
        port = f":{parsed.port}" if parsed.port else ""
        return ProxyEndpoint(
            server=f"{parsed.scheme}://{parsed.hostname}{port}",
            username=parsed.username,
            password=parsed.password,
            country=country,
            session_id=session_id,
            url=url,
        )
