import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProxyEndpoint:
    server: str  # scheme://host:port, không kèm thông tin đăng nhập
    username: str | None
    password: str | None = field(repr=False)  # không lộ trong log/traceback
    country: str = "vn"
    session_id: str = ""
    url: str = field(default="", repr=False)  # URL đầy đủ (có mật khẩu) cho HTTP client

    @property
    def id(self) -> str:
        return f"{self.country}:{self.session_id}"


class ProxyProvider(Protocol):
    def new_endpoint(self, country: str) -> ProxyEndpoint: ...


class StaticProxyProvider:
    """Sinh endpoint từ một hoặc nhiều template có thể chứa {country} và {session}.

    Ví dụ: http://USER-country-{country}-session-{session}:PASS@gate.provider.com:7777
    Mỗi lần gọi new_endpoint tạo session id mới, nghĩa là IP residential mới (sticky). Nhiều
    template (nhiều nhà cung cấp, cách nhau dấu phẩy) được dùng xoay vòng: một nhà cung cấp hỏng
    không làm ngừng toàn bộ.
    """

    def __init__(
        self,
        template: str | list[str],
        id_factory: Callable[[], str] = lambda: secrets.token_hex(4),
    ) -> None:
        templates = template if isinstance(template, list) else template.split(",")
        self._templates = [t.strip() for t in templates if t.strip()]
        if not self._templates:
            raise ValueError("no proxy template configured")
        self._id_factory = id_factory
        self._next = 0

    @property
    def templates(self) -> list[str]:
        return list(self._templates)

    def new_endpoint(self, country: str) -> ProxyEndpoint:
        session_id = self._id_factory()
        template = self._templates[self._next % len(self._templates)]
        self._next += 1
        url = template.format(country=country, session=session_id)
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
