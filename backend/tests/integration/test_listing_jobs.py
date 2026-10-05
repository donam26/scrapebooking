"""Vòng đời listing (D8): verify URL người dùng dán, gợi ý cùng khách sạn trên kênh khác."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.registry import channels
from app.clock import FixedClock
from app.collector.base import ListingBlocked, ListingNotFound
from app.db.models import Hotel, Listing
from app.domain.models import ListingCandidate, ListingIdentity, ListingQuery, ListingRef
from app.worker.listing_jobs import (
    ListingJobDeps,
    ListingRetry,
    run_discover_listing,
    run_verify_listing,
)
from tests.integration.seed import add_hotel, add_listing

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
CARAVELLE = ListingIdentity(
    external_id="74331",
    name="Caravelle Saigon",
    url="https://www.booking.com/hotel/vn/caravelle-saigon.html",
    address="19 - 23 Lam Son Square, District 1",
    city="Ho Chi Minh City",
    country_code="vn",
    lat=10.7763,
    lng=106.7036,
    star_rating=Decimal("5"),
)


class ScriptedChannel:
    """Collector kênh giả: verify/suggest trả kết quả hoặc ném lỗi đã kịch bản."""

    def __init__(
        self,
        identity: ListingIdentity | Exception = CARAVELLE,
        candidates: list[ListingCandidate] | Exception | None = None,
    ) -> None:
        self.identity = identity
        self.candidates = candidates or []
        self.verified: list[ListingRef] = []
        self.queries: list[ListingQuery] = []

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        self.verified.append(listing)
        if isinstance(self.identity, Exception):
            raise self.identity
        return self.identity

    async def suggest(self, query: ListingQuery) -> list[ListingCandidate]:
        self.queries.append(query)
        if isinstance(self.candidates, Exception):
            raise self.candidates
        return self.candidates


def _deps(
    db: AsyncSession, collector: ScriptedChannel, channel: str = "booking"
) -> tuple[ListingJobDeps, list[tuple[int, str]]]:
    discovered: list[tuple[int, str]] = []

    async def enqueue_discover(hotel_id: int, ch: str) -> None:
        discovered.append((hotel_id, ch))

    deps = ListingJobDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector,  # type: ignore[arg-type]
        clock=FixedClock(NOW),
        channel=channel,
        enqueue_discover=enqueue_discover,
    )
    return deps, discovered


async def _unverified(db: AsyncSession) -> tuple[int, int]:
    hotel = await add_hotel(db, "vn/caravelle-saigon", status="unverified")
    listing = (await db.execute(select(Listing).where(Listing.hotel_id == hotel.id))).scalar_one()
    await db.commit()
    return hotel.id, listing.id


async def test_verify_success_activates_listing_fills_hotel_and_discovers(db: AsyncSession) -> None:
    hotel_id, listing_id = await _unverified(db)
    collector = ScriptedChannel()
    deps, discovered = _deps(db, collector)
    assert await run_verify_listing(deps, listing_id, final_attempt=False) == "active"
    assert [(r.channel, r.listing_key) for r in collector.verified] == [
        ("booking", "vn/caravelle-saigon")
    ]
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    hotel = await db.get(Hotel, hotel_id)
    assert listing is not None and hotel is not None
    assert (listing.status, listing.external_id, listing.name) == (
        "active",
        "74331",
        "Caravelle Saigon",
    )
    assert listing.verified_at == NOW and listing.last_error is None
    assert (hotel.name, hotel.address, hotel.city) == (
        "Caravelle Saigon",
        "19 - 23 Lam Son Square, District 1",
        "Ho Chi Minh City",
    )
    assert (hotel.lat, hotel.lng, hotel.star_rating) == (10.7763, 106.7036, Decimal("5.0"))
    # Tìm cùng khách sạn trên mọi kênh khác đang thu được (chưa có listing).
    expected = sorted(str(c) for c, i in channels().items() if i.collectable and c != "booking")
    assert sorted(ch for _, ch in discovered) == expected
    assert all(h == hotel_id for h, _ in discovered)


async def test_verify_does_not_overwrite_known_hotel_fields(db: AsyncSession) -> None:
    hotel_id, listing_id = await _unverified(db)
    hotel = await db.get(Hotel, hotel_id)
    assert hotel is not None
    hotel.name, hotel.lat, hotel.lng = "Caravelle", 1.0, 2.0
    await db.commit()
    deps, _ = _deps(db, ScriptedChannel())
    await run_verify_listing(deps, listing_id, final_attempt=False)
    db.expire_all()
    hotel = await db.get(Hotel, hotel_id)
    assert hotel is not None and (hotel.name, hotel.lat, hotel.lng) == ("Caravelle", 1.0, 2.0)
    assert hotel.address == "19 - 23 Lam Son Square, District 1"  # trường còn trống thì điền


async def test_verify_not_found_marks_broken(db: AsyncSession) -> None:
    _, listing_id = await _unverified(db)
    deps, discovered = _deps(db, ScriptedChannel(identity=ListingNotFound("http 404")))
    assert await run_verify_listing(deps, listing_id, final_attempt=False) == "broken"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "broken"
    assert listing.last_error == "not_found" and discovered == []


async def test_verify_blocked_retries_then_keeps_status(db: AsyncSession) -> None:
    _, listing_id = await _unverified(db)
    deps, _ = _deps(db, ScriptedChannel(identity=ListingBlocked("waf")))
    with pytest.raises(ListingRetry):
        await run_verify_listing(deps, listing_id, final_attempt=False)
    assert await run_verify_listing(deps, listing_id, final_attempt=True) == "blocked"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "unverified"
    assert listing.last_error == "blocked"  # chi tiết nằm trong log, không lưu cho tenant


async def test_verify_unexpected_error_retries_then_records_error(db: AsyncSession) -> None:
    # Timeout proxy, mạng chập chờn: thử lại như bị chặn; lần cuối ghi lỗi, giữ trạng thái.
    _, listing_id = await _unverified(db)
    deps, discovered = _deps(db, ScriptedChannel(identity=TimeoutError("proxy timeout")))
    with pytest.raises(ListingRetry, match="proxy timeout"):
        await run_verify_listing(deps, listing_id, final_attempt=False)
    assert await run_verify_listing(deps, listing_id, final_attempt=True) == "error"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "unverified"
    assert listing.last_error == "error: TimeoutError" and discovered == []


async def test_verify_missing_listing(db: AsyncSession) -> None:
    deps, _ = _deps(db, ScriptedChannel())
    assert await run_verify_listing(deps, 999, final_attempt=True) == "missing"


async def test_verify_duplicate_of_other_hotel_listing_is_broken(db: AsyncSession) -> None:
    # Hai URL khác nhau cùng trỏ một khách sạn của kênh: không quét trùng.
    other = await add_hotel(db, "vn/caravelle-old")
    old = (await db.execute(select(Listing).where(Listing.hotel_id == other.id))).scalar_one()
    old.external_id = "74331"
    other_id = other.id
    _, listing_id = await _unverified(db)
    deps, discovered = _deps(db, ScriptedChannel())
    assert await run_verify_listing(deps, listing_id, final_attempt=False) == "duplicate"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "broken"
    assert f"#{other_id}" in (listing.last_error or "") and discovered == []


def _candidate(key: str, score: float, external_id: str | None = None) -> ListingCandidate:
    return ListingCandidate(
        channel="agoda",
        listing_key=key,
        url=f"https://www.agoda.com/{key}/hotel/ho-chi-minh-city-vn.html",
        name="Caravelle Saigon Hotel",
        external_id=external_id,
        score=score,
    )


async def _named_hotel(db: AsyncSession) -> int:
    hotel = await add_hotel(db, "vn/caravelle-saigon", name="Caravelle Saigon")
    hotel.city, hotel.lat, hotel.lng = "Ho Chi Minh City", 10.7763, 106.7036
    await db.commit()
    return hotel.id


async def test_discover_creates_suggested_listing_with_score(db: AsyncSession) -> None:
    hotel_id = await _named_hotel(db)
    collector = ScriptedChannel(
        candidates=[_candidate("caravelle-hotel", 0.92, "1985199"), _candidate("other", 0.8)]
    )
    deps, _ = _deps(db, collector, channel="agoda")
    assert await run_discover_listing(deps, hotel_id, final_attempt=False) == "suggested"
    assert collector.queries == [
        ListingQuery("Caravelle Saigon", "Ho Chi Minh City", "vn", 10.7763, 106.7036)
    ]
    row = (await db.execute(select(Listing).where(Listing.channel == "agoda"))).scalar_one()
    assert (row.status, row.listing_key, row.external_id, row.match_score) == (
        "suggested",
        "caravelle-hotel",
        "1985199",
        Decimal("0.920"),
    )
    # Đã có listing trên kênh này (kể cả đang gợi ý): không tìm lại.
    assert await run_discover_listing(deps, hotel_id, final_attempt=False) == "exists"
    assert len(collector.queries) == 1


async def test_discover_ignores_weak_matches(db: AsyncSession) -> None:
    hotel_id = await _named_hotel(db)
    deps, _ = _deps(db, ScriptedChannel(candidates=[_candidate("x", 0.69)]), channel="agoda")
    assert await run_discover_listing(deps, hotel_id, final_attempt=False) == "none"
    assert (await db.execute(select(Listing).where(Listing.channel == "agoda"))).first() is None


async def test_discover_skips_candidate_owned_by_another_hotel(db: AsyncSession) -> None:
    hotel_id = await _named_hotel(db)
    other = await add_hotel(db, "vn/other")
    taken = await add_listing(db, other.id, "agoda", "caravelle-hotel")
    taken.external_id = "1985199"
    await db.commit()
    candidates = [_candidate("caravelle-hotel", 0.95, "1985199"), _candidate("caravelle-2", 0.8)]
    deps, _ = _deps(db, ScriptedChannel(candidates=candidates), channel="agoda")
    assert await run_discover_listing(deps, hotel_id, final_attempt=False) == "suggested"
    row = (
        await db.execute(
            select(Listing).where(Listing.hotel_id == hotel_id, Listing.channel == "agoda")
        )
    ).scalar_one()
    assert row.listing_key == "caravelle-2"


async def test_discover_conflict_on_listing_key_of_other_hotel(db: AsyncSession) -> None:
    hotel_id = await _named_hotel(db)
    other = await add_hotel(db, "vn/other")
    await add_listing(db, other.id, "agoda", "caravelle-hotel")  # chưa biết external_id
    await db.commit()
    deps, _ = _deps(
        db, ScriptedChannel(candidates=[_candidate("caravelle-hotel", 0.95)]), channel="agoda"
    )
    assert await run_discover_listing(deps, hotel_id, final_attempt=False) == "conflict"


async def test_discover_needs_hotel_name_and_retries_when_blocked(db: AsyncSession) -> None:
    unnamed = await add_hotel(db, "vn/unnamed")
    await db.commit()
    deps, _ = _deps(db, ScriptedChannel(), channel="agoda")
    assert await run_discover_listing(deps, unnamed.id, final_attempt=False) == "no-hotel"
    assert await run_discover_listing(deps, 999, final_attempt=False) == "no-hotel"

    hotel_id = await _named_hotel(db)
    deps, _ = _deps(db, ScriptedChannel(candidates=ListingBlocked("captcha")), channel="agoda")
    with pytest.raises(ListingRetry):
        await run_discover_listing(deps, hotel_id, final_attempt=False)
    assert await run_discover_listing(deps, hotel_id, final_attempt=True) == "blocked"
