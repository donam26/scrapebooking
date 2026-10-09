"""Danh mục kênh (thuần, không I/O): mã, tên hiển thị, nhận diện URL.

Sản phẩm chỉ theo dõi **Booking.com** (10/2026: bỏ Agoda, iVIVU, Trip.com, Mytour, Traveloka,
Expedia). Cột `channel` trong DB vẫn giữ (luôn là "booking") để không đổi khoá các bảng quan sát.
API import được module này mà không kéo Playwright/curl_cffi; phần thu dữ liệu nằm ở
`app/collector/booking/`, được worker nạp qua `app.collector.factory`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from app.i18n import DEFAULT_LOCALE, t


class ChannelCode(StrEnum):
    BOOKING = "booking"


BOOKING = str(ChannelCode.BOOKING)
CHANNEL_ORDER = {str(c): i for i, c in enumerate(ChannelCode)}


def sort_channels(codes: Iterable[str]) -> list[str]:
    return sorted(set(codes), key=lambda c: (CHANNEL_ORDER.get(c, 99), c))


class UnsupportedUrl(ValueError):
    """URL không phải trang một khách sạn trên kênh được hỗ trợ. Mang mã `url.<key>` + tham số;
    `message(locale)` là câu cho người dùng, `str(exc)` là bản tiếng Việt (CLI, log)."""

    def __init__(self, key: str, **params: str) -> None:
        self.key = key
        self.params = params
        super().__init__(self.message(DEFAULT_LOCALE))

    def message(self, locale: str) -> str:
        return t(locale, f"url.{self.key}", **self.params)


@dataclass(frozen=True)
class ListingUrl:
    channel: str
    listing_key: str  # khoá ổn định trong kênh (UNIQUE(channel, listing_key))
    url: str  # URL chuẩn hoá không kèm ngày
    country_code: str | None = None
    external_id: str | None = None


# Hàm nhận diện: trả None nếu không phải host của kênh; raise UnsupportedUrl nếu đúng host nhưng
# không phải trang một khách sạn.
UrlParser = Callable[[str], ListingUrl | None]


@dataclass(frozen=True)
class ChannelInfo:
    code: ChannelCode
    name: str
    example_url: str
    parse_url: UrlParser
    collectable: bool  # đã có collector chạy thật

    @property
    def hosts(self) -> tuple[str, ...]:
        """Tên miền gốc của kênh ("booking.com") để giao diện nhận diện URL."""
        host = (urlparse(self.example_url).hostname or "").lower()
        return (".".join(host.split(".")[-2:]),) if host else ()


def host_matches(url: str, *domains: str) -> bool:
    host = (urlparse(url.strip()).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def _channels() -> dict[ChannelCode, ChannelInfo]:
    # Import trễ để tránh vòng import; urls.py chỉ dùng thư viện chuẩn.
    from app.collector.booking.urls import parse_url as booking_url

    info = ChannelInfo(
        ChannelCode.BOOKING,
        "Booking.com",
        "https://www.booking.com/hotel/vn/ten-khach-san.html",
        booking_url,
        collectable=True,
    )
    return {info.code: info}


_CACHE: dict[ChannelCode, ChannelInfo] | None = None


def channels() -> dict[ChannelCode, ChannelInfo]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _channels()
    return _CACHE


def channel_name(code: str) -> str:
    info = channels().get(ChannelCode(code)) if code in ChannelCode.__members__.values() else None
    return info.name if info else code


def parse_listing_url(url: str) -> ListingUrl:
    """Nhận diện kênh từ URL. Raise UnsupportedUrl (thông điệp cho người dùng, theo ngôn ngữ)."""
    raw = url.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsupportedUrl("bad_scheme")
    if len(raw) > 2000:
        raise UnsupportedUrl("too_long")
    for info in channels().values():
        try:
            result = info.parse_url(raw)
        except UnsupportedUrl:
            raise
        except ValueError as exc:  # VD chữ số Unicode trong id: không phải URL khách sạn hợp lệ
            raise UnsupportedUrl("channel_invalid", channel=info.name) from exc
        if result is not None:
            if len(result.listing_key) > 300 or len(result.url) > 2000:
                raise UnsupportedUrl("channel_too_long", channel=info.name)
            return result
    supported = ", ".join(i.name for i in channels().values() if i.collectable)
    raise UnsupportedUrl("unsupported", channels=supported)
