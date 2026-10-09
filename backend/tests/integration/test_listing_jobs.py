"""Vòng đời listing: verify URL Booking.com người dùng dán."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.base import ListingBlocked, ListingNotFound
from app.db.models import Hotel, Listing
from app.domain.models import ListingIdentity, ListingRef
from app.worker.listing_jobs import (
    ListingJobDeps,
    ListingRetry,
    run_verify_listing,
)
from tests.integration.seed import add_hotel

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
    """Collector giả: verify trả kết quả hoặc ném lỗi đã kịch bản."""

    def __init__(self, identity: ListingIdentity | Exception = CARAVELLE) -> None:
        self.identity = identity
        self.verified: list[ListingRef] = []

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        self.verified.append(listing)
        if isinstance(self.identity, Exception):
            raise self.identity
        return self.identity


def _deps(db: AsyncSession, collector: ScriptedChannel) -> tuple[ListingJobDeps, None]:
    deps = ListingJobDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector,  # type: ignore[arg-type]
        clock=FixedClock(NOW),
        channel="booking",
    )
    return deps, None


async def _unverified(db: AsyncSession) -> tuple[int, int]:
    hotel = await add_hotel(db, "vn/caravelle-saigon", status="unverified")
    listing = (await db.execute(select(Listing).where(Listing.hotel_id == hotel.id))).scalar_one()
    await db.commit()
    return hotel.id, listing.id


async def test_verify_success_activates_listing_and_fills_hotel(db: AsyncSession) -> None:
    hotel_id, listing_id = await _unverified(db)
    collector = ScriptedChannel()
    deps, _ = _deps(db, collector)
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
    deps, _ = _deps(db, ScriptedChannel(identity=ListingNotFound("http 404")))
    assert await run_verify_listing(deps, listing_id, final_attempt=False) == "broken"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "broken"
    assert listing.last_error == "not_found"


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
    deps, _ = _deps(db, ScriptedChannel(identity=TimeoutError("proxy timeout")))
    with pytest.raises(ListingRetry, match="proxy timeout"):
        await run_verify_listing(deps, listing_id, final_attempt=False)
    assert await run_verify_listing(deps, listing_id, final_attempt=True) == "error"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "unverified"
    assert listing.last_error == "error: TimeoutError"


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
    deps, _ = _deps(db, ScriptedChannel())
    assert await run_verify_listing(deps, listing_id, final_attempt=False) == "duplicate"
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None and listing.status == "broken"
    assert f"#{other_id}" in (listing.last_error or "")
