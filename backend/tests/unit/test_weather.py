"""Gom dự báo OpenWeather 3 giờ thành từng ngày và cache theo toạ độ."""

from datetime import UTC, date, datetime

import httpx
import pytest

from app.market import weather
from app.market.weather import WeatherUnavailable, fetch_weather, parse_forecast


def _item(iso: str, temp: float, desc: str, icon: str, pop: float = 0.0) -> dict:
    ts = int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp())
    return {
        "dt": ts,
        "main": {"temp": temp, "feels_like": temp + 1, "humidity": 70},
        "weather": [{"description": desc, "icon": icon}],
        "pop": pop,
    }


PAYLOAD = {
    "city": {"name": "Ho Chi Minh City", "timezone": 7 * 3600},
    "list": [
        # 16:00 UTC = 23:00 giờ VN ngày 02/10
        _item("2026-10-02T16:00:00", 27.0, "mây rải rác", "03n"),
        # 18:00 UTC = 01:00 ngày 03/10
        _item("2026-10-02T18:00:00", 25.5, "mưa nhẹ", "10n", 0.4),
        _item("2026-10-03T03:00:00", 32.2, "mưa nhẹ", "10d", 0.8),
        _item("2026-10-03T09:00:00", 29.0, "mây đen u ám", "04d"),
    ],
}


def test_parse_groups_by_local_day() -> None:
    w = parse_forecast(PAYLOAD)
    assert w.location == "Ho Chi Minh City"
    assert [d.date for d in w.days] == [date(2026, 10, 2), date(2026, 10, 3)]
    d3 = w.days[1]
    assert (d3.temp_min, d3.temp_max) == (25.5, 32.2)
    assert d3.description == "mưa nhẹ" and d3.icon == "10d" and d3.pop == 0.8
    assert w.current is not None and w.current.temp == 27.0 and w.current.humidity == 70


def test_parse_empty_list() -> None:
    w = parse_forecast({"city": {}, "list": []})
    assert w.current is None and w.days == [] and w.location is None


async def test_fetch_uses_cache_for_30_minutes() -> None:
    weather._cache.clear()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        a = await fetch_weather(10.7757, 106.7014, "k", client=client, now=1000.0)
        b = await fetch_weather(10.7761, 106.7009, "k", client=client, now=1000.0 + 60)
        c = await fetch_weather(10.7757, 106.7014, "k", client=client, now=1000.0 + 31 * 60)
    assert a is b and c is not a
    assert len(calls) == 2
    assert calls[0].url.params["units"] == "metric" and calls[0].url.params["lat"] == "10.78"
    weather._cache.clear()


async def test_failure_hides_key_and_is_remembered_briefly() -> None:
    weather._cache.clear()
    weather._failed.clear()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"message": "Invalid API key"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WeatherUnavailable) as err:
            await fetch_weather(10.77, 106.70, "secret-key", client=client, now=0.0)
        with pytest.raises(WeatherUnavailable):
            await fetch_weather(10.77, 106.70, "secret-key", client=client, now=60.0)
        with pytest.raises(WeatherUnavailable):
            await fetch_weather(10.77, 106.70, "secret-key", client=client, now=200.0)
    assert "secret-key" not in str(err.value) and str(err.value) == "http 401"
    assert calls == 2
    weather._failed.clear()
