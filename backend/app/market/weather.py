"""Thời tiết cho thẻ Terminal+: dự báo 5 ngày (bước 3 giờ) của OpenWeather tại toạ độ khách sạn.

Không đặt OPENWEATHER_API_KEY thì không gọi ra ngoài (thẻ báo cần cấu hình). Kết quả cache
trong bộ nhớ tiến trình 30 phút theo toạ độ làm tròn 2 chữ số và ngôn ngữ mô tả, đủ dưới hạn mức
gói miễn phí.
"""

import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
CACHE_TTL_S = 30 * 60
# Lỗi (key sai, hết hạn mức, mạng) được nhớ ngắn để không gọi lại OpenWeather mỗi request.
FAIL_TTL_S = 120


class WeatherUnavailable(Exception):
    """Không lấy được dự báo. Thông điệp không chứa URL (URL có API key)."""


@dataclass(frozen=True)
class WeatherNow:
    temp: float
    feels_like: float
    humidity: int
    description: str
    icon: str


@dataclass(frozen=True)
class WeatherDay:
    date: date
    temp_min: float
    temp_max: float
    description: str
    icon: str
    # Xác suất mưa cao nhất trong ngày (0–1).
    pop: float


@dataclass(frozen=True)
class Weather:
    location: str | None
    current: WeatherNow | None
    days: list[WeatherDay]


def parse_forecast(payload: dict[str, Any]) -> Weather:
    """Gom các mốc 3 giờ thành từng ngày theo giờ địa phương của thành phố."""
    city = payload.get("city") or {}
    offset = timedelta(seconds=int(city.get("timezone") or 0))
    items: list[dict[str, Any]] = payload.get("list") or []
    by_day: dict[date, list[dict[str, Any]]] = {}
    for it in items:
        local = datetime.fromtimestamp(int(it["dt"]), tz=UTC) + offset
        by_day.setdefault(local.date(), []).append(it)

    days: list[WeatherDay] = []
    for d, rows in sorted(by_day.items()):
        temps = [float(r["main"]["temp"]) for r in rows]
        weather = [r["weather"][0] for r in rows if r.get("weather")]
        # Mô tả thường gặp nhất trong ngày; biểu tượng ban ngày nếu có.
        desc = Counter(w["description"] for w in weather).most_common(1)[0][0] if weather else ""
        icons = [w["icon"] for w in weather if w.get("description") == desc]
        icon = next((i for i in icons if i.endswith("d")), icons[0] if icons else "")
        days.append(
            WeatherDay(
                date=d,
                temp_min=round(min(temps), 1),
                temp_max=round(max(temps), 1),
                description=desc,
                icon=icon,
                pop=round(max(float(r.get("pop") or 0) for r in rows), 2),
            )
        )

    current = None
    if items:
        first = items[0]
        w = (first.get("weather") or [{}])[0]
        current = WeatherNow(
            temp=round(float(first["main"]["temp"]), 1),
            feels_like=round(float(first["main"].get("feels_like", first["main"]["temp"])), 1),
            humidity=int(first["main"].get("humidity", 0)),
            description=str(w.get("description", "")),
            icon=str(w.get("icon", "")),
        )
    return Weather(location=city.get("name"), current=current, days=days)


_cache: dict[tuple[float, float, str], tuple[float, Weather]] = {}
_failed: dict[tuple[float, float, str], tuple[float, str]] = {}


async def fetch_weather(
    lat: float,
    lng: float,
    api_key: str,
    *,
    lang: str = "vi",
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
) -> Weather:
    """Dự báo tại (lat, lng), mô tả theo `lang` (mã OpenWeather: vi, en), cache 30 phút; lỗi nhớ
    2 phút. Ném WeatherUnavailable khi lỗi."""
    key = (round(lat, 2), round(lng, 2), lang)
    ts = time.monotonic() if now is None else now
    hit = _cache.get(key)
    if hit and ts - hit[0] < CACHE_TTL_S:
        return hit[1]
    failed = _failed.get(key)
    if failed and ts - failed[0] < FAIL_TTL_S:
        raise WeatherUnavailable(failed[1])
    params: dict[str, str | float] = {
        "lat": key[0],
        "lon": key[1],
        "units": "metric",
        "lang": lang,
        "appid": api_key,
    }
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=10) as own:
                resp = await own.get(FORECAST_URL, params=params)
        else:
            resp = await client.get(FORECAST_URL, params=params)
        if resp.status_code != 200:
            raise WeatherUnavailable(f"http {resp.status_code}")
        weather = parse_forecast(resp.json())
    except WeatherUnavailable as exc:
        _failed[key] = (ts, str(exc))
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        # Chỉ ghi tên lỗi: thông điệp của httpx có thể chứa URL kèm API key.
        reason = type(exc).__name__
        _failed[key] = (ts, reason)
        raise WeatherUnavailable(reason) from None
    _failed.pop(key, None)
    _cache[key] = (ts, weather)
    return weather
