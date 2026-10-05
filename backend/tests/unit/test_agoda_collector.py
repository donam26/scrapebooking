"""AgodaCollector với HTTP giả (fixture thật trong tests/fixtures/agoda): luồng probe/verify/suggest,
chặn -> đổi session, hết phòng qua room-grid, sai tiền tệ."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.clock import FixedClock
from app.collector.agoda import collector as agoda_collector
from app.collector.agoda.collector import AgodaCollector, AgodaHttp, build
from app.collector.base import ListingBlocked, ListingNotFound
from app.collector.factory import ChannelKeys, CollectorDeps
from app.collector.fetch import FetchResponse
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import ScrapeSession
from app.domain.models import ListingQuery, ListingRef, ProbeMethod, ProbeStatus

MELIA_URL = "https://www.agoda.com/vi-vn/melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn.html"
MELIA = ListingRef(1, "agoda", "melia-vinpearl-phu-quoc/hotel/phu-quoc-island-vn", MELIA_URL, "vn")
MELIA_ID = ListingRef(1, "agoda", MELIA.listing_key, MELIA_URL, "vn", external_id="1985199")
CAMIA = ListingRef(2, "agoda", "id/3647146", "https://www.agoda.com/vi-vn/x", "vn", "3647146")


@dataclass
class Call:
    method: str
    url: str
    headers: dict[str, str]
    session_id: str
    payload: dict[str, Any] | None


Route = Callable[[str, str], tuple[int, str]]


@dataclass
class FakeHttp:
    route: Route
    calls: list[Call] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        session: ScrapeSession,
        payload: dict[str, Any] | None = None,
    ) -> FetchResponse:
        self.calls.append(Call(method, url, headers, session.id, payload))
        status, text = self.route(method, url)
        return FetchResponse(status=status, text=text, url=url, elapsed_ms=5)

    async def close(self, session_id: str) -> None:
        self.closed.append(session_id)

    async def close_all(self) -> None:
        self.closed.append("*")


class CountingBudget:
    def __init__(self) -> None:
        self.n = 0

    async def acquire(self) -> None:
        self.n += 1


async def no_sleep(_: float) -> None:
    return None


def _deps(budget: CountingBudget | None = None) -> CollectorDeps:
    return CollectorDeps(
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        clock=FixedClock(datetime(2026, 10, 1, 8, 0, tzinfo=UTC)),
        limiter=RateLimiter(min_interval=0, jitter=0, sleep=no_sleep),
        currency="VND",
        headless=True,
        session_max_age=timedelta(minutes=20),
        session_max_requests=400,
        budget=budget or CountingBudget(),
    )


def _collector(
    route: Route, budget: CountingBudget | None = None
) -> tuple[AgodaCollector, FakeHttp]:
    http = FakeHttp(route)
    return AgodaCollector(_deps(budget), http=http, backoff=no_sleep), http


def _fixture(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / "agoda" / name).read_text(encoding="utf-8")


def test_worker_constants() -> None:
    assert isinstance(agoda_collector.PARSER_VERSION, str) and agoda_collector.PARSER_VERSION
    assert agoda_collector.DROPDOWN_CAP == 99  # không có dropdown: tồn phòng qua badge_count


def test_build_returns_collector_with_real_http() -> None:
    collector = build(_deps())
    assert isinstance(collector, AgodaCollector)
    assert isinstance(collector._http, AgodaHttp)


async def test_probe_ok_single_api_call(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_2026-10-20.json")
    budget = CountingBudget()
    collector, http = _collector(lambda m, u: (200, body), budget)
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.OK
    assert result.method == ProbeMethod.API
    assert result.checkout == date(2026, 10, 21)
    assert (result.external_id, result.http_status) == ("1985199", 200)
    assert result.hotel_name == "Melia Vinpearl Phú Quốc (Melia Vinpearl Phu Quoc)"
    assert len(result.offers) == 7
    assert result.raw_html == body
    assert result.duration_ms == 5  # thời gian mạng, không tính giãn cách
    assert result.session_id == http.calls[0].session_id
    assert len(http.calls) == 1 and budget.n == 1
    call = http.calls[0]
    assert call.method == "GET"
    assert "hotel_id=1985199" in call.url and "checkIn=2026-10-20&los=1" in call.url
    assert call.headers["cr-currency-code"] == "VND"
    assert call.headers["Referer"] == MELIA_URL


async def test_probe_resolves_property_id_from_page_once(fixtures_dir: Path) -> None:
    page = _fixture(fixtures_dir, "property_page_snippet.html")
    data = _fixture(fixtures_dir, "melia_2026-10-20.json")
    collector, http = _collector(lambda m, u: (200, page if u == MELIA_URL else data))
    first = await collector.probe(MELIA, date(2026, 10, 20), 1, 2)
    second = await collector.probe(MELIA, date(2026, 10, 20), 1, 2)
    assert first.status == second.status == ProbeStatus.OK
    assert [c.url == MELIA_URL for c in http.calls] == [True, False, False]
    assert http.calls[0].headers["Accept"].startswith("text/html")


async def test_currency_mismatch_is_error_without_offers(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_usd_2026-10-20.json")
    collector, _ = _collector(lambda m, u: (200, body))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error == "currency_mismatch:USD"
    assert result.offers == ()
    assert result.raw_html == body


async def test_other_dates_are_not_recorded(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_2026-10-20.json")
    collector, _ = _collector(lambda m, u: (200, body))
    result = await collector.probe(MELIA_ID, date(2026, 10, 21), 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error and result.error.startswith("agoda showed other dates")


async def test_sold_out_confirmed_by_room_grid(fixtures_dir: Path) -> None:
    data = _fixture(fixtures_dir, "camia_sold_out_2026-10-03.json")
    grid = _fixture(fixtures_dir, "camia_room_grid_2026-10-03.json")
    collector, http = _collector(lambda m, u: (200, grid if m == "POST" else data))
    result = await collector.probe(CAMIA, date(2026, 10, 3), 1, 2)
    assert result.status == ProbeStatus.SOLD_OUT
    assert result.raw_html == grid  # bằng chứng hết phòng
    assert result.duration_ms == 10
    assert result.hotel_name == "Camia Resort & Spa"
    post = http.calls[1]
    assert post.url == "https://www.agoda.com/api/v1/property/room-grid"
    assert post.payload is not None and post.payload["propertyId"] == "3647146"
    assert post.headers["ag-user-id"] and post.headers["x-gate-meta"]
    assert post.headers["cr-currency-code"] == "VND"


async def test_empty_grid_without_room_grid_answer_is_no_rooms(fixtures_dir: Path) -> None:
    data = _fixture(fixtures_dir, "camia_sold_out_2026-10-03.json")
    collector, _ = _collector(lambda m, u: (403, "") if m == "POST" else (200, data))
    result = await collector.probe(CAMIA, date(2026, 10, 3), 1, 2)
    assert result.status == ProbeStatus.NO_ROOMS_1N
    assert result.raw_html == data


async def test_blocked_twice_retires_both_sessions(fixtures_dir: Path) -> None:
    collector, http = _collector(lambda m, u: (403, "<html>Access Denied</html>"))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    sessions = [c.session_id for c in http.calls]
    assert len(sessions) == 2 and sessions[0] != sessions[1]
    assert http.closed == sessions


async def test_blocked_then_ok_uses_new_session(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_2026-10-20.json")
    answers = iter([(200, "<html><title>Just a moment</title></html>"), (200, body)])
    collector, http = _collector(lambda m, u: next(answers))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.OK
    assert result.session_id == http.calls[1].session_id != http.calls[0].session_id


async def test_server_error_retried_once(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_2026-10-20.json")
    answers = iter([(502, "bad gateway"), (200, body)])
    collector, http = _collector(lambda m, u: next(answers))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.OK
    assert http.calls[0].session_id == http.calls[1].session_id


async def test_unknown_property_and_missing_page_are_not_found(fixtures_dir: Path) -> None:
    # Payload đầy đủ (isDataReady, không error) mà không có khách sạn: Agoda nói rõ id không tồn tại.
    body = _fixture(fixtures_dir, "not_found.json")
    collector, http = _collector(lambda m, u: (200, body))
    assert (await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)).error == "not_found"
    assert http.closed == []  # không phải chặn: giữ session
    collector, _ = _collector(lambda m, u: (404, "<html>not found</html>"))
    result = await collector.probe(MELIA, date(2026, 10, 20), 1, 2)
    assert (result.status, result.error) == (ProbeStatus.ERROR, "not_found")


def _incomplete(fixtures_dir: Path) -> str:
    data = json.loads(_fixture(fixtures_dir, "not_found.json"))
    data["roomGridData"]["isDataReady"] = False
    return json.dumps(data)


async def test_json_200_without_hotel_info_is_blocked_not_broken(fixtures_dir: Path) -> None:
    # JSON 200 thiếu hotelInfo.name ở payload chưa đủ dữ liệu: chặn mềm → đổi session, BLOCKED
    # (trước đây là not_found → listing broken vĩnh viễn).
    body = _incomplete(fixtures_dir)
    collector, http = _collector(lambda m, u: (200, body))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    assert result.error == "incomplete payload: no hotelInfo"
    assert http.closed == [http.calls[0].session_id]
    collector, _ = _collector(lambda m, u: (200, body))
    with pytest.raises(ListingBlocked):
        await collector.verify(MELIA_ID)


async def test_html_200_without_property_id_is_blocked(fixtures_dir: Path) -> None:
    collector, http = _collector(lambda m, u: (200, "<html><body>Please wait…</body></html>"))
    result = await collector.probe(MELIA, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.BLOCKED
    assert http.closed == [http.calls[0].session_id]
    with pytest.raises(ListingBlocked):
        await collector.verify(MELIA)


async def test_retired_session_closes_client_and_clears_rate_limiter(fixtures_dir: Path) -> None:
    body = _fixture(fixtures_dir, "melia_2026-10-20.json")
    deps = _deps()
    http = FakeHttp(lambda m, u: (200, body))
    collector = AgodaCollector(deps, http=http, backoff=no_sleep)
    await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    sid = http.calls[0].session_id
    assert sid in deps.limiter._last
    await collector._sessions.retire(await collector._sessions.get("vn", "x"), "expired")
    assert http.closed == [sid] and sid not in deps.limiter._last


async def test_transport_error_after_retry_is_error() -> None:
    def boom(m: str, u: str) -> tuple[int, str]:
        raise ConnectionError("proxy down")

    collector, http = _collector(boom)
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.ERROR
    assert result.error and result.error.startswith("transport: ConnectionError")
    assert len(http.calls) == 2


async def test_verify_resolves_id_then_reads_identity(fixtures_dir: Path) -> None:
    page = _fixture(fixtures_dir, "property_page_snippet.html")
    data = _fixture(fixtures_dir, "melia_2026-10-20.json")
    collector, http = _collector(lambda m, u: (200, page if u == MELIA_URL else data))
    identity = await collector.verify(MELIA)
    assert identity.external_id == "1985199"
    assert identity.url and identity.url.endswith(
        "/vinpearl-discovery-2-phu-quoc_2/hotel/phu-quoc-island-vn.html"
    )
    assert identity.lat is not None and identity.star_rating is not None
    assert "checkIn" not in http.calls[1].url  # bản không kèm ngày


async def test_verify_missing_page_or_unknown_id_is_not_found(fixtures_dir: Path) -> None:
    collector, _ = _collector(lambda m, u: (404, ""))
    with pytest.raises(ListingNotFound):
        await collector.verify(MELIA)
    body = _fixture(fixtures_dir, "not_found.json")
    collector, _ = _collector(lambda m, u: (200, body))
    with pytest.raises(ListingNotFound):
        await collector.verify(MELIA_ID)


@pytest.mark.parametrize("answer", [(403, ""), (500, "oops")])
async def test_verify_blocked_or_http_error_is_retry_later(answer: tuple[int, str]) -> None:
    collector, _ = _collector(lambda m, u: answer)
    with pytest.raises(ListingBlocked):
        await collector.verify(MELIA_ID)


async def test_suggest_blocked_is_retry_later() -> None:
    collector, _ = _collector(lambda m, u: (429, ""))
    with pytest.raises(ListingBlocked):
        await collector.suggest(ListingQuery("Caravelle Saigon"))


async def test_suggest_tries_name_variants_until_hits(fixtures_dir: Path) -> None:
    suggest = _fixture(fixtures_dir, "suggest_caravelle.json")
    dateless = _fixture(fixtures_dir, "caravelle_dateless.json")

    def route(m: str, u: str) -> tuple[int, str]:
        if "Suggest" not in u:
            return 200, dateless
        # Như Booking: tên có tiền tố loại hình không ra kết quả.
        return 200, '{"ViewModelList": []}' if "Kh%C3%A1ch" in u else suggest

    collector, http = _collector(route)
    candidates = await collector.suggest(ListingQuery("Khách sạn Caravelle Saigon"))
    assert [c.external_id for c in candidates] == ["10971"]
    assert "searchText=Kh%C3%A1ch%20s%E1%BA%A1n%20Caravelle%20Saigon&" in http.calls[0].url
    assert "searchText=Caravelle%20Saigon&" in http.calls[1].url


async def test_suggest_enriches_with_url_and_coordinates(fixtures_dir: Path) -> None:
    suggest = _fixture(fixtures_dir, "suggest_caravelle.json")
    dateless = _fixture(fixtures_dir, "caravelle_dateless.json")
    collector, http = _collector(lambda m, u: (200, suggest if "Suggest" in u else dateless))
    query = ListingQuery("Caravelle Saigon", "Hồ Chí Minh", "vn", 10.7763, 106.7036)
    candidates = await collector.suggest(query)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.channel == "agoda" and c.external_id == "10971"
    assert c.listing_key == "caravelle-saigon-hotel/hotel/ho-chi-minh-city-vn"
    assert (
        c.url == "https://www.agoda.com/vi-vn/caravelle-saigon-hotel/hotel/ho-chi-minh-city-vn.html"
    )
    assert c.name == "Caravelle Saigon Hotel" and c.country_code == "vn"
    assert c.score == 1.0
    assert "searchText=Caravelle%20Saigon" in http.calls[0].url


async def test_suggest_falls_back_to_id_url_when_details_blocked(fixtures_dir: Path) -> None:
    suggest = _fixture(fixtures_dir, "suggest_caravelle.json")
    collector, _ = _collector(lambda m, u: (200, suggest) if "Suggest" in u else (403, ""))
    candidates = await collector.suggest(ListingQuery("Caravelle Saigon"))
    assert [(c.listing_key, c.lat, c.score) for c in candidates] == [("id/10971", None, 1.0)]


async def test_calendar_is_unsupported() -> None:
    collector, http = _collector(lambda m, u: (200, "{}"))
    result = await collector.fetch_calendar(MELIA_ID, date(2026, 10, 20), 30, 2)
    assert (result.ok, result.error) == (False, "unsupported")
    assert http.calls == []


async def test_close_closes_http_clients() -> None:
    collector, http = _collector(lambda m, u: (200, "{}"))
    await collector.close()
    assert http.closed == ["*"]


@pytest.mark.parametrize("status", [403, 429])
async def test_rate_limit_statuses_count_as_blocked(status: int) -> None:
    collector, _ = _collector(lambda m, u: (status, ""))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert result.status == ProbeStatus.BLOCKED


async def test_503_outage_is_retried_then_error_without_burning_session() -> None:
    collector, http = _collector(lambda m, u: (503, "Service Unavailable"))
    result = await collector.probe(MELIA_ID, date(2026, 10, 20), 1, 2)
    assert (result.status, result.error) == (ProbeStatus.ERROR, "http 503")
    assert len(http.calls) == 2 and http.calls[0].session_id == http.calls[1].session_id
    assert http.closed == []


async def test_gate_headers_use_keys_from_settings(fixtures_dir: Path) -> None:
    data = _fixture(fixtures_dir, "camia_sold_out_2026-10-03.json")
    grid = _fixture(fixtures_dir, "camia_room_grid_2026-10-03.json")
    deps = _deps()
    deps.keys = ChannelKeys(agoda_initiator_api_key="key-2", agoda_initiator_version="7_1")
    http = FakeHttp(lambda m, u: (200, grid if m == "POST" else data))
    await AgodaCollector(deps, http=http, backoff=no_sleep).probe(CAMIA, date(2026, 10, 3), 1, 2)
    post = http.calls[1]
    assert post.headers["ag-initiator-api-key"] == "key-2"
    assert post.headers["ag-initiator-version"] == "7_1"
