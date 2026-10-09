import secrets
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from app.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ProxyEndpoint:
    server: str  # scheme://host:port, không kèm thông tin đăng nhập
    username: str | None
    password: str | None = field(repr=False)  # không lộ trong log/traceback
    country: str = "vn"
    session_id: str = ""
    url: str = field(default="", repr=False)  # URL đầy đủ (có mật khẩu) cho HTTP client
    # Nhãn template sinh ra endpoint ("#1 gate.provider.com:7777"): báo lỗi/khoẻ theo template.
    provider: str = ""

    @property
    def id(self) -> str:
        return f"{self.country}:{self.session_id}"


class ProxyProvider(Protocol):
    def new_endpoint(self, country: str) -> ProxyEndpoint: ...


def template_label(template: str, index: int) -> str:
    """Nhãn ổn định của template thứ `index` (không có mật khẩu): "#1 host:port".

    Scheduler (kiểm tra sức khoẻ) và worker (chọn proxy) dùng cùng thứ tự PROXY_URL_TEMPLATE nên
    cùng nhãn."""
    url = template.format(country="vn", session="x")
    parsed = urlparse(url)
    host = f"{parsed.hostname}:{parsed.port}" if parsed.port else str(parsed.hostname)
    return f"#{index + 1} {host}"


class StaticProxyProvider:
    """Sinh endpoint từ một hoặc nhiều template có thể chứa {country} và {session}.

    Ví dụ: http://USER-country-{country}-session-{session}:PASS@gate.provider.com:7777
    Mỗi lần gọi new_endpoint tạo session id mới, nghĩa là IP residential mới (sticky).

    Nhiều template (nhiều nhà cung cấp, cách nhau dấu phẩy) được xoay vòng **theo sức khoẻ**
    (roadmap 0.2): template lỗi liên tiếp `fail_threshold` lần (bootstrap phiên thất bại, 407…) bị
    ngắt `cooldown_s` giây; template mà lượt kiểm tra định kỳ của scheduler báo hỏng (chia sẻ qua
    Redis, `set_shared_down`) cũng bị bỏ qua. Khi mọi template đều hỏng thì vẫn xoay vòng như cũ
    (thà thử còn hơn dừng hẳn) — lượt quét lúc đó do scheduler hoãn (0.3).
    """

    def __init__(
        self,
        template: str | list[str],
        id_factory: Callable[[], str] = lambda: secrets.token_hex(4),
        *,
        fail_threshold: int = 3,
        cooldown_s: float = 600.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        templates = template if isinstance(template, list) else template.split(",")
        self._templates = [t.strip() for t in templates if t.strip()]
        if not self._templates:
            raise ValueError("no proxy template configured")
        self._labels = [template_label(t, i) for i, t in enumerate(self._templates)]
        self._id_factory = id_factory
        self._next = 0
        self._fail_threshold = fail_threshold
        self._cooldown_s = cooldown_s
        self._now = monotonic
        self._fails: dict[str, int] = {}
        self._down_until: dict[str, float] = {}
        self._shared_down: set[str] = set()

    @property
    def templates(self) -> list[str]:
        return list(self._templates)

    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    def healthy(self, label: str) -> bool:
        return label not in self._shared_down and self._now() >= self._down_until.get(label, 0.0)

    def healthy_labels(self) -> list[str]:
        return [lb for lb in self._labels if self.healthy(lb)]

    def set_shared_down(self, labels: Iterable[str]) -> None:
        """Template mà lần kiểm tra proxy gần nhất (scheduler) báo hỏng."""
        down = {lb for lb in labels if lb in self._labels}
        if down != self._shared_down:
            log.info("proxy_shared_health", down=sorted(down))
        self._shared_down = down

    def report_failure(self, endpoint: ProxyEndpoint) -> None:
        label = endpoint.provider
        if label not in self._labels:
            return
        n = self._fails.get(label, 0) + 1
        self._fails[label] = n
        if n >= self._fail_threshold:
            self._down_until[label] = self._now() + self._cooldown_s
            self._fails[label] = 0
            log.warning("proxy_template_tripped", proxy=label, cooldown_s=self._cooldown_s)

    def report_success(self, endpoint: ProxyEndpoint) -> None:
        if endpoint.provider in self._labels:
            self._fails[endpoint.provider] = 0
            self._down_until.pop(endpoint.provider, None)

    def _pick(self) -> int:
        n = len(self._templates)
        for k in range(n):
            i = (self._next + k) % n
            if self.healthy(self._labels[i]):
                return i
        return self._next % n

    def new_endpoint(self, country: str) -> ProxyEndpoint:
        session_id = self._id_factory()
        i = self._pick()
        self._next = i + 1
        template = self._templates[i]
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
            provider=self._labels[i],
        )


def report_proxy(provider: object, endpoint: ProxyEndpoint, ok: bool) -> None:
    """Báo kết quả dùng proxy cho provider nếu nó hỗ trợ (provider giả trong test thì bỏ qua)."""
    fn = getattr(provider, "report_success" if ok else "report_failure", None)
    if callable(fn):
        fn(endpoint)
