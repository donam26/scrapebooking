"""IvivuCollector với minter/fetcher giả: token dùng một lần, làm mới session khi token hỏng."""

import json
from collections import deque
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.clock import FixedClock
from app.collector.base import ListingNotFound
from app.collector.factory import CollectorDeps
from app.collector.fetch import FetchResponse
from app.collector.ivivu import collector as ivivu_collector
from app.collector.ivivu.collector import IvivuCollector
from app.collector.proxy import ProxyEndpoint, StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import ScrapeSession
from app.domain.models import DemandKind, ListingQuery, ListingRef, ProbeMethod, ProbeStatus

MELIA = ListingRef(
    hotel_id=1,
    channel="ivivu",
    listing_key="khach-san-phu-quoc/khu-nghi-duong-melia-vinpearl-phu-quoc",
    url="https://www.ivivu.com/khach-san-phu-quoc/khu-nghi-duong-melia-vinpearl-phu-quoc",
    country_code="vn",
    external_id="377594",
)
DAY = date(2026, 10, 12)


async def no_sleep(_: float) -> None:
    return None


class FakeMinter:
    def __init__(self, tokens: list[str | None]) -> None:
        self.tokens = deque(tokens)
        self.user_agent = "Mozilla/5.0 Chrome/153"
        self.cookies = {"__cf_bm": "x"}
        self.closed = False

    async def mint(self) -> str | None:
        return self.tokens.popleft() if self.tokens else "tok"

    async def close(self) -> None:
        self.closed = True


class FakeFetcher:
    def __init__(self, *responses: FetchResponse | Exception) -> None:
        self.queue: deque[FetchResponse | Exception] = deque(responses)
        self.posts: list[tuple[str, dict[str, Any], dict[str, str], str]] = []
        self.closed: list[str] = []

    async def get(self, url: str, session: ScrapeSession) -> FetchResponse:
        raise AssertionError("price API only")

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse:
        self.posts.append((url, payload, headers, session.id))
        item = self.queue.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self, session_id: str) -> None:
        self.closed.append(session_id)


def resp(status: int, text: str) -> FetchResponse:
    return FetchResponse(
        status=status, text=text, url="https://apiportal.ivivu.com/x", elapsed_ms=5
    )


class Harness:
    def __init__(
        self,
        fixtures_dir: Path,
        fetcher: FakeFetcher,
        minters: list[FakeMinter] | None = None,
        public: dict[str, tuple[int, str]] | None = None,
        max_requests: int = 400,
    ) -> None:
        self.fixtures = fixtures_dir / "ivivu"
        self.minters = deque(minters or [])
        self.launched: list[FakeMinter] = []
        self.public_calls: list[str] = []
        self.public = (
            public
            if public is not None
            else {
                "TopSale24hByHotel": (200, self.read("topsale24h_melia.json")),
                "searchhotel": (200, self.read("searchhotel_melia.json")),
            }
        )
        self.clock = FixedClock(datetime(2026, 10, 1, 8, 0, tzinfo=UTC))
        deps = CollectorDeps(
            proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
            clock=self.clock,
            limiter=RateLimiter(min_interval=0, jitter=0, sleep=no_sleep),
            currency="VND",
            headless=True,
            session_max_age=timedelta(minutes=20),
            session_max_requests=max_requests,
        )
        self.fetcher = fetcher
        self.collector = IvivuCollector(
            deps,
            fetcher=fetcher,
            minter_factory=self.launch,
            public_get=self.get,
            backoff=no_sleep,
        )

    def read(self, name: str) -> str:
        return (self.fixtures / name).read_text()

    async def launch(self, proxy: ProxyEndpoint, warmup_url: str) -> FakeMinter:
        minter = self.minters.popleft() if self.minters else FakeMinter([])
        self.launched.append(minter)
        return minter

    async def get(self, url: str) -> tuple[int, str]:
        self.public_calls.append(url)
        for part, answer in self.public.items():
            if part in url:
                return answer
        return 404, "not found"


def price_ok(fixtures_dir: Path) -> FetchResponse:
    return resp(200, (fixtures_dir / "ivivu" / "price_melia_2026-10-12.json").read_text())


def invalid_token(fixtures_dir: Path) -> FetchResponse:
    return resp(403, (fixtures_dir / "ivivu" / "invalid_token_403.json").read_text())


async def test_probe_ok_uses_fresh_token_and_api_method(fixtures_dir: Path) -> None:
    h = Harness(fixtures_dir, FakeFetcher(price_ok(fixtures_dir)), [FakeMinter(["t1"])])
    r = await h.collector.probe(MELIA, DAY, nights=1, adults=2)
    assert r.status == ProbeStatus.OK and r.method == ProbeMethod.API
    assert r.external_id == "377594" and r.hotel_name == "Khu nghỉ dưỡng Melia Vinpearl Phú Quốc"
    assert r.checkout == date(2026, 10, 13) and r.http_status == 200
    url, payload, headers, sid = h.fetcher.posts[0]
    assert url.endswith("/contracting/HotelSearchReqContractAppV2")
    assert payload["hotelID"] == 377594 and payload["checkInDate"] == "2026-10-12"
    assert headers["X-ivv-key"] == "t1" and r.session_id == sid
    assert r.raw_html is not None and json.loads(r.raw_html)["Hotels"][0]["HotelCode"] == "377594"
    kinds = {s.kind: s.value for s in r.demand_signals}
    assert kinds == {DemandKind.ROOMS_SOLD_24H: 2, DemandKind.BOOKINGS_MONTH: 17}


async def test_one_session_and_cached_demand_across_probes(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher(price_ok(fixtures_dir), price_ok(fixtures_dir))
    h = Harness(fixtures_dir, fetcher, [FakeMinter(["t1", "t2"])])
    await h.collector.probe(MELIA, DAY, 1, 2)
    r = await h.collector.probe(MELIA, DAY + timedelta(days=1), 1, 2)
    assert len(h.launched) == 1
    assert [p[2]["X-ivv-key"] for p in fetcher.posts] == ["t1", "t2"]  # mỗi request một token
    assert len(h.public_calls) == 2  # TopSale + searchhotel chỉ gọi một lần trong TTL
    assert len(r.demand_signals) == 2


async def test_invalid_token_refreshes_session_once_then_ok(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher(invalid_token(fixtures_dir), price_ok(fixtures_dir))
    first, second = FakeMinter(["bad"]), FakeMinter(["good"])
    h = Harness(fixtures_dir, fetcher, [first, second])
    r = await h.collector.probe(MELIA, DAY, 1, 2)
    assert r.status == ProbeStatus.OK
    assert first.closed and not second.closed
    assert fetcher.closed == [fetcher.posts[0][3]]
    assert [p[2]["X-ivv-key"] for p in fetcher.posts] == ["bad", "good"]


async def test_invalid_token_twice_is_blocked(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher(invalid_token(fixtures_dir), invalid_token(fixtures_dir))
    h = Harness(fixtures_dir, fetcher, [FakeMinter([]), FakeMinter([])])
    r = await h.collector.probe(MELIA, DAY, 1, 2)
    assert r.status == ProbeStatus.BLOCKED and r.error == "invalid_token"
    assert r.http_status == 403 and len(h.launched) == 2


async def test_token_mint_failure_is_blocked_without_price_call(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher()
    h = Harness(fixtures_dir, fetcher, [FakeMinter([None]), FakeMinter([None])])
    r = await h.collector.probe(MELIA, DAY, 1, 2)
    assert r.status == ProbeStatus.BLOCKED and r.error == "token_unavailable"
    assert fetcher.posts == []


async def test_transport_error_retries_with_new_token(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher(TimeoutError("slow"), price_ok(fixtures_dir))
    h = Harness(fixtures_dir, fetcher, [FakeMinter(["t1", "t2"])])
    r = await h.collector.probe(MELIA, DAY, 1, 2)
    assert r.status == ProbeStatus.OK and len(h.launched) == 1
    assert [p[2]["X-ivv-key"] for p in fetcher.posts] == ["t1", "t2"]


async def test_session_renewed_after_max_requests(fixtures_dir: Path) -> None:
    fetcher = FakeFetcher(price_ok(fixtures_dir), price_ok(fixtures_dir))
    h = Harness(fixtures_dir, fetcher, max_requests=3)  # 1 probe = 2 request token + 1 giá
    await h.collector.probe(MELIA, DAY, 1, 2)
    await h.collector.probe(MELIA, DAY, 1, 2)
    assert len(h.launched) == 2 and h.launched[0].closed


async def test_probe_resolves_hotel_id_from_page_once(fixtures_dir: Path) -> None:
    listing = ListingRef(**{**MELIA.__dict__, "external_id": None})
    fetcher = FakeFetcher(price_ok(fixtures_dir), price_ok(fixtures_dir))
    h = Harness(fixtures_dir, fetcher)
    h.public["khu-nghi-duong-melia-vinpearl-phu-quoc"] = (
        200,
        h.read("hotel_page_melia.html"),
    )
    await h.collector.probe(listing, DAY, 1, 2)
    await h.collector.probe(listing, DAY, 1, 2)
    assert fetcher.posts[1][1]["hotelID"] == 377594
    assert sum("khach-san-phu-quoc" in u for u in h.public_calls) == 1


async def test_unknown_hotel_page_is_not_found(fixtures_dir: Path) -> None:
    listing = ListingRef(**{**MELIA.__dict__, "external_id": None})
    h = Harness(fixtures_dir, FakeFetcher())
    r = await h.collector.probe(listing, DAY, 1, 2)
    assert r.status == ProbeStatus.ERROR and r.error == "not_found" and h.launched == []
    h.public[listing.listing_key] = (200, "<html><body>Trang vùng</body></html>")
    with pytest.raises(ListingNotFound):
        await h.collector.verify(listing)


async def test_suggest_scores_and_filters_country(fixtures_dir: Path) -> None:
    items = json.loads((fixtures_dir / "ivivu" / "searchhotel_melia.json").read_text())
    items[1]["countryCode"] = "IT"  # nước khác: loại
    h = Harness(fixtures_dir, FakeFetcher(), public={"searchhotel": (200, json.dumps(items))})
    out = await h.collector.suggest(
        ListingQuery(name="Melia Vinpearl Phu Quoc", lat=10.3579746, lng=103.84963725)
    )
    assert out[0].external_id == "377594" and out[0].score == 1.0
    assert out[0].listing_key == MELIA.listing_key and out[0].url == MELIA.url
    assert "577334" not in {c.external_id for c in out}
    assert len(out) <= 5


async def test_suggest_also_searches_core_name_and_merges(fixtures_dir: Path) -> None:
    # Tên đầy đủ chỉ ra khách sạn khác (như "Rex Hotel Saigon" → các khách sạn "Saigon");
    # tìm thêm theo tên riêng mới ra đúng khách sạn. Gộp, không trùng.
    items = json.loads((fixtures_dir / "ivivu" / "searchhotel_melia.json").read_text())
    h = Harness(fixtures_dir, FakeFetcher(), public={})
    h.public["keyword=melia+vinpearl+phu+quoc"] = (200, json.dumps(items))
    h.public["searchhotel"] = (200, json.dumps(items[1:]))
    out = await h.collector.suggest(ListingQuery(name="Melia Vinpearl Phu Quoc Resort"))
    assert [u.split("keyword=")[1] for u in h.public_calls] == [
        "Melia+Vinpearl+Phu+Quoc+Resort",
        "melia+vinpearl+phu+quoc",
    ]
    ids = [c.external_id for c in out]
    assert ids[0] == "377594" and len(ids) == len(set(ids))


async def test_suggest_stops_after_strong_match(fixtures_dir: Path) -> None:
    h = Harness(fixtures_dir, FakeFetcher(), public={})
    h.public["searchhotel"] = (200, h.read("searchhotel_melia.json"))
    out = await h.collector.suggest(ListingQuery(name="Khu nghỉ dưỡng Melia Vinpearl Phú Quốc"))
    assert out[0].external_id == "377594" and len(h.public_calls) == 1


async def test_suggest_tries_english_name_then_core_name(fixtures_dir: Path) -> None:
    h = Harness(fixtures_dir, FakeFetcher(), public={"searchhotel": (200, "[]")})
    assert await h.collector.suggest(ListingQuery(name="Rex Hotel Saigon")) == []
    assert [u.split("keyword=")[1] for u in h.public_calls] == ["Rex+Hotel+Saigon", "rex"]


def test_worker_constants() -> None:
    assert ivivu_collector.DROPDOWN_CAP == 99
    assert ivivu_collector.PARSER_VERSION == "2"


async def test_calendar_is_unsupported(fixtures_dir: Path) -> None:
    h = Harness(fixtures_dir, FakeFetcher())
    cal = await h.collector.fetch_calendar(MELIA, DAY, 30, 2)
    assert not cal.ok and cal.error == "unsupported"
