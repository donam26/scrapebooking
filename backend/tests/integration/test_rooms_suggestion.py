"""Gợi ý "Số phòng" đo trên Booking.com: job đo (lịch nbRooms giả, không gọi mạng), cron chọn
listing cần đo, verify đẩy job đo, API đọc/xác nhận gợi ý."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auth import hash_password
from app.clock import FixedClock
from app.db.models import Hotel, Listing, RoomType, Tenant, TenantHotel, User
from app.domain.models import CalendarDay, CalendarResult, ListingIdentity, ListingRef
from app.worker.capacity_probe import (
    INCOMPLETE_RETRY,
    NO_INVENTORY_RETRY,
    REMEASURE_AFTER,
    WINDOW_DAYS,
    WINDOW_OFFSET_DAYS,
    due_capacity_listings,
    run_measure_capacity,
)
from app.worker.listing_jobs import ListingJobDeps, run_verify_listing
from tests.integration.seed import add_hotel
from tests.integration.test_api import _login, _seed

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
GRAPHQL_500 = "unexpected payload: [{'message': 'Internal Server Error'}]"


class BookingCalendar:
    """Lịch Booking giả: còn bán ở nbRooms = n khi n ≤ `units` (đêm chẵn của cửa sổ). `errors`:
    các n trả lỗi (mỗi lần gọi tiêu một phần tử); `error` là câu lỗi trả về."""

    def __init__(
        self,
        units: int | None,
        errors: Iterable[int] = (),
        error: str = GRAPHQL_500,
        empty: bool = False,
    ) -> None:
        self.units = units
        self.errors = list(errors)
        self.error = error
        self.empty = empty
        self.calls: list[tuple[int, date, int, int, int]] = []

    async def fetch_calendar(
        self, hotel: ListingRef, start: date, days: int, adults: int, rooms: int = 1
    ) -> CalendarResult:
        self.calls.append((hotel.hotel_id, start, days, adults, rooms))
        if rooms in self.errors:
            self.errors.remove(rooms)
            return CalendarResult(ok=False, error=self.error)
        if self.empty:
            return CalendarResult(ok=True, days=())
        sells = self.units is not None and rooms <= self.units
        return CalendarResult(
            ok=True,
            days=tuple(
                CalendarDay(start + timedelta(days=i), sells and i % 2 == 0, 1, None)
                for i in range(days)
            ),
        )

    async def verify(self, listing: ListingRef) -> ListingIdentity:
        return ListingIdentity(
            external_id="6309114",
            name="MEANDER Saigon",
            url=listing.url,
            address=None,
            city="Ho Chi Minh City",
            country_code="vn",
            lat=10.7824,
            lng=106.7053,
            star_rating=None,
        )


def _deps(db: AsyncSession, collector: BookingCalendar, **kw: object) -> ListingJobDeps:
    return ListingJobDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector,  # type: ignore[arg-type]
        clock=FixedClock(NOW),
        channel="booking",
        **kw,  # type: ignore[arg-type]
    )


async def _tracked(db: AsyncSession, slug: str, *, status: str = "active") -> Listing:
    tenant = (await db.execute(select(Tenant).where(Tenant.name == "T"))).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name="T", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00"])
        db.add(tenant)
        await db.flush()
    hotel = await add_hotel(db, slug, name=slug, status=status)
    db.add(TenantHotel(tenant_id=tenant.id, hotel_id=hotel.id, role="competitor", active=True))
    await db.commit()
    return (await db.execute(select(Listing).where(Listing.hotel_id == hotel.id))).scalar_one()


async def _reload(db: AsyncSession, listing_id: int) -> Listing:
    db.expire_all()
    listing = await db.get(Listing, listing_id)
    assert listing is not None
    return listing


async def test_measurement_stores_the_most_units_booking_sells_in_one_night(
    db: AsyncSession,
) -> None:
    listing = await _tracked(db, "vn/meander-saigon")
    cal = BookingCalendar(units=74)
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "measured"
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_capped) == (74, False)
    assert stored.capacity_checked_at == NOW
    assert stored.capacity_next_at == NOW + REMEASURE_AFTER
    # "Booking từng mở bán ≥N phòng/đêm" cũng nâng theo (trước đó chỉ thấy các đêm gần).
    assert (stored.rooms_max_seen, stored.rooms_max_seen_at) == (74, NOW)
    # Cửa sổ đêm xa cố định; mỗi phòng một người lớn; 9 request lịch.
    start = NOW.date() + timedelta(days=WINDOW_OFFSET_DAYS)
    assert {(c[1], c[2]) for c in cal.calls} == {(start, WINDOW_DAYS)}
    assert all(adults == rooms for *_, adults, rooms in cal.calls)
    assert [c[4] for c in cal.calls[:2]] == [1, 100] and len(cal.calls) <= 9


async def test_large_hotel_is_only_a_lower_bound(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/the-reverie-saigon")
    cal = BookingCalendar(units=286)
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "measured"
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_capped, len(cal.calls)) == (100, True, 2)


async def test_result_never_decreases_fresh_is_skipped_and_force_replaces(
    db: AsyncSession,
) -> None:
    listing = await _tracked(db, "vn/caravelle")
    listing.capacity_max, listing.capacity_capped = 80, True
    listing.capacity_next_at = NOW - timedelta(hours=1)
    listing.rooms_max_seen = 95
    await db.commit()
    cal = BookingCalendar(units=60)  # đêm xa lần này đông hơn
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "measured"
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_capped, stored.rooms_max_seen) == (80, True, 95)
    calls = len(cal.calls)
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "fresh"
    assert len(cal.calls) == calls
    # Operator ép đo lại: kết quả mới thay kết quả cũ (kể cả cờ chạm trần đo nhầm).
    assert await run_measure_capacity(_deps(db, cal), listing.id, force=True) == "measured"
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_capped) == (60, False)


async def test_transient_errors_keep_the_floor_and_retry_tomorrow(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/meander-saigon")
    cal = BookingCalendar(units=74, errors=[75, 75])
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "incomplete"
    stored = await _reload(db, listing.id)
    # Còn bán ở 50 trước khi lịch lỗi: giữ cận dưới, chưa chốt lần đo, đo lại sau 1 ngày.
    assert (stored.capacity_max, stored.capacity_checked_at) == (50, None)
    assert stored.capacity_next_at == NOW + INCOMPLETE_RETRY
    assert [c[4] for c in cal.calls].count(75) == 2  # hỏi lại một lần


async def test_blocked_calendar_stops_without_another_request(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/meander-saigon")
    cal = BookingCalendar(units=74, errors=[50], error="blocked")
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "incomplete"
    assert [c[4] for c in cal.calls] == [1, 100, 50]
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_next_at) == (1, NOW + INCOMPLETE_RETRY)


async def test_empty_calendar_answer_is_not_read_as_no_rooms(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/meander-saigon")
    cal = BookingCalendar(units=74, empty=True)
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "incomplete"
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_checked_at) == (None, None)


async def test_window_without_rooms_is_measured_again_in_a_week(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/closed")
    assert await run_measure_capacity(_deps(db, BookingCalendar(None)), listing.id) == (
        "no_inventory"
    )
    stored = await _reload(db, listing.id)
    assert (stored.capacity_max, stored.capacity_checked_at) == (None, NOW)
    assert stored.capacity_next_at == NOW + NO_INVENTORY_RETRY


async def test_paused_listing_is_not_measured(db: AsyncSession) -> None:
    listing = await _tracked(db, "vn/paused", status="paused")
    cal = BookingCalendar(units=10)
    assert await run_measure_capacity(_deps(db, cal), listing.id) == "inactive"
    assert cal.calls == []


async def test_due_listings_still_need_a_room_count_and_are_tracked(db: AsyncSession) -> None:
    never = await _tracked(db, "vn/never")
    stale = await _tracked(db, "vn/stale")
    fresh = await _tracked(db, "vn/fresh")
    paused = await _tracked(db, "vn/paused", status="paused")
    known = await _tracked(db, "vn/known")  # đã có số phòng: không cần gợi ý
    stale.capacity_next_at = NOW - timedelta(hours=1)
    fresh.capacity_next_at = NOW + timedelta(days=2)
    await db.execute(update(Hotel).where(Hotel.id == known.hotel_id).values(rooms_total=40))
    untracked = await add_hotel(db, "vn/untracked")  # không tenant nào theo dõi
    gone = Tenant(name="Gone", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00"], active=False)
    db.add(gone)
    await db.flush()
    off = await add_hotel(db, "vn/off")  # chỉ tenant đã ngừng theo dõi
    db.add(TenantHotel(tenant_id=gone.id, hotel_id=off.id, role="competitor", active=True))
    await db.commit()
    assert untracked.id and paused.id
    due = await due_capacity_listings(db, NOW)
    assert due == [(never.id, "booking"), (stale.id, "booking")]
    everything = await due_capacity_listings(db, NOW, include_fresh=True)
    assert [d[0] for d in everything] == [never.id, stale.id, fresh.id]
    assert await due_capacity_listings(db, NOW, limit=1) == [(never.id, "booking")]


async def test_daily_cron_enqueues_due_listings_spaced_out(db: AsyncSession) -> None:
    from app.jobs.settings import capacity_catch_up

    first = await _tracked(db, "vn/new-competitor")
    second = await _tracked(db, "vn/another-competitor")
    sent: list[tuple[int, str, timedelta | None]] = []

    class Queue:
        async def enqueue_capacity(
            self,
            listing_id: int,
            channel: str,
            force: bool = False,
            defer_by: timedelta | None = None,
        ) -> None:
            sent.append((listing_id, channel, defer_by))

    ctx = {
        "session_factory": async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        "queue": Queue(),
    }
    assert await capacity_catch_up(ctx) == 2
    assert sent == [
        (first.id, "booking", timedelta(0)),
        (second.id, "booking", timedelta(minutes=2)),
    ]


async def test_verified_listing_asks_for_a_capacity_measurement(db: AsyncSession) -> None:
    hotel = await add_hotel(db, "vn/meander-saigon", status="unverified")
    listing = (await db.execute(select(Listing).where(Listing.hotel_id == hotel.id))).scalar_one()
    await db.commit()
    asked: list[int] = []

    async def on_verified(listing_id: int) -> None:
        asked.append(listing_id)

    deps = _deps(db, BookingCalendar(units=10), on_verified=on_verified)
    assert await run_verify_listing(deps, listing.id, final_attempt=False) == "active"
    assert asked == [listing.id]

    async def broken_queue(listing_id: int) -> None:
        raise ConnectionError("redis down")

    # Hàng đợi lỗi không làm hỏng verify: cron hằng ngày đo bù.
    deps = _deps(db, BookingCalendar(units=10), on_verified=broken_queue)
    assert await run_verify_listing(deps, listing.id, final_attempt=False) == "active"


# ---------------------------------------------------------------- API


async def _measure(
    db: AsyncSession,
    hotel_id: int,
    units: int,
    *,
    capped: bool = False,
    beds: bool = False,
    seen: int = 54,
) -> Listing:
    listing = (await db.execute(select(Listing).where(Listing.hotel_id == hotel_id))).scalar_one()
    listing.capacity_max, listing.capacity_capped = units, capped
    listing.capacity_checked_at = NOW
    listing.rooms_max_seen = seen
    if beds:
        db.add(
            RoomType(
                hotel_id=hotel_id,
                channel="booking",
                external_room_id="630911401",
                name="Bed in 8-Bed Mixed Dormitory Room",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
    await db.commit()
    return listing


async def test_watchlist_shows_the_booking_rooms_suggestion(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    listing = await _measure(db, ids["comp"], 94, beds=True)
    await _login(client, "view@a.com", "view-pass-1")
    items = {i["hotel"]["id"]: i["hotel"] for i in (await client.get("/watchlist")).json()}
    s = items[ids["comp"]]["rooms_suggestion"]
    assert s == {
        "rooms": 94,
        "lower_bound": False,
        "capped": False,
        "includes_beds": True,
        "confirmable": False,
        "measured_at": "2026-10-16T03:00:00Z",
        "source_url": listing.url,
    }
    assert items[ids["own"]]["rooms_suggestion"] is None  # chưa đo các đêm xa


async def test_confirm_sets_the_room_count_once(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    listing = await _measure(db, ids["comp"], 74)
    await _login(client, "admin@a.com", "admin-pass-1")
    url = f"/watchlist/{ids['comp']}/rooms-suggestion/confirm"
    r = await client.post(url, json={"rooms": 74})
    assert r.status_code == 200, r.text
    hotel = r.json()["hotel"]
    assert (hotel["rooms_total"], hotel["rooms_total_source"]) == (74, listing.url)
    assert hotel["rooms_total_updated_at"] is not None
    again = await client.post(url, json={"rooms": 74})
    assert again.status_code == 409 and again.json()["detail"] == "room count already confirmed"
    # Số đã xác nhận vẫn sửa tay được như trước (tenant là người theo dõi duy nhất).
    r = await client.patch(f"/watchlist/{ids['comp']}", json={"rooms_total": 70})
    assert r.status_code == 200 and r.json()["hotel"]["rooms_total"] == 70


async def test_confirm_refuses_missing_stale_lower_bound_or_bed_suggestions(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _measure(db, ids["comp"], 74)
    await _measure(db, ids["own"], 100, capped=True)
    await _login(client, "view@a.com", "view-pass-1")
    comp = f"/watchlist/{ids['comp']}/rooms-suggestion/confirm"
    assert (await client.post(comp, json={"rooms": 74})).status_code == 403  # chỉ xem
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(comp, json={"rooms": 70})
    assert r.status_code == 409 and r.json()["detail"] == "room count suggestion changed; reload"
    r = await client.post(f"/watchlist/{ids['own']}/rooms-suggestion/confirm", json={"rooms": 100})
    assert r.status_code == 409 and r.json()["detail"].startswith(
        "room count suggestion is only a lower bound"
    )
    r = await client.post(f"/watchlist/{ids['other']}/rooms-suggestion/confirm", json={"rooms": 1})
    assert r.status_code == 404  # khách sạn của tenant khác
    # Lượt quét thường từng thấy nhiều hơn kết quả đo: cận dưới.
    await _measure(db, ids["comp"], 74, seen=80)
    r = await client.post(comp, json={"rooms": 80})
    assert r.status_code == 409 and "lower bound" in r.json()["detail"]
    # Giường dorm: hiện số nhưng không dùng làm số phòng.
    await _measure(db, ids["comp"], 94, beds=True)
    r = await client.post(comp, json={"rooms": 94})
    assert r.status_code == 409 and r.json()["detail"].startswith(
        "room count suggestion counts dorm beds"
    )
    listing = (
        await db.execute(select(Listing).where(Listing.hotel_id == ids["comp"]))
    ).scalar_one()
    listing.capacity_checked_at = None  # chưa đo các đêm xa: không có gợi ý
    await db.commit()
    r = await client.post(comp, json={"rooms": 94})
    assert r.status_code == 409 and r.json()["detail"] == "no room count suggestion for this hotel"
    hotel = (await db.execute(select(Hotel).where(Hotel.id == ids["comp"]))).scalar_one()
    await db.refresh(hotel)
    assert hotel.rooms_total is None


async def test_confirm_never_overwrites_a_count_typed_meanwhile(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Có người nhập số ngay giữa lúc kiểm tra và lúc ghi: cập nhật có điều kiện thua, giữ số đó."""
    from app.api.routers import watchlist

    ids = await _seed(db)
    await _measure(db, ids["comp"], 74)
    real = watchlist.hotel_out

    async def racing(session: AsyncSession, hotel: Hotel):  # type: ignore[no-untyped-def]
        out = await real(session, hotel)
        async with async_sessionmaker(db.bind)() as other:  # type: ignore[arg-type]
            await other.execute(
                update(Hotel)
                .where(Hotel.id == hotel.id)
                .values(rooms_total=80, rooms_total_source="https://hotel.example/rooms")
            )
            await other.commit()
        return out

    monkeypatch.setattr(watchlist, "hotel_out", racing)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(f"/watchlist/{ids['comp']}/rooms-suggestion/confirm", json={"rooms": 74})
    assert r.status_code == 409 and r.json()["detail"] == "room count already confirmed"
    hotel = (await db.execute(select(Hotel).where(Hotel.id == ids["comp"]))).scalar_one()
    await db.refresh(hotel)
    assert (hotel.rooms_total, hotel.rooms_total_source) == (80, "https://hotel.example/rooms")


async def test_booking_estimate_on_a_shared_hotel_can_be_replaced_by_another_tenant(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Số lấy từ gợi ý đo trên Booking chỉ là ước tính: tenant khác cùng theo dõi thay được bằng
    số công bố; số nhập tay thì vẫn chỉ người theo dõi duy nhất/operator sửa được."""
    ids = await _seed(db)
    await _measure(db, ids["comp"], 74)
    db.add_all(
        [
            TenantHotel(tenant_id=ids["t2"], hotel_id=ids["comp"], role="competitor", active=True),
            User(
                tenant_id=ids["t2"],
                email="admin@b.com",
                password_hash=hash_password("admin-pass-2"),
                role="tenant_admin",
                active=True,
            ),
        ]
    )
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    url = f"/watchlist/{ids['comp']}/rooms-suggestion/confirm"
    assert (await client.post(url, json={"rooms": 74})).status_code == 200
    await _login(client, "admin@b.com", "admin-pass-2")
    r = await client.patch(
        f"/watchlist/{ids['comp']}",
        json={"rooms_total": 82, "rooms_total_source": "https://comp.example/rooms"},
    )
    assert r.status_code == 200, r.text
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.patch(f"/watchlist/{ids['comp']}", json={"rooms_total": 74})
    assert r.status_code == 403 and "room count is shared" in r.json()["detail"]


async def test_replacing_the_booking_url_forgets_the_old_measurement(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    listing = await _measure(db, ids["comp"], 94, capped=True)
    listing.capacity_next_at = NOW + REMEASURE_AFTER
    listing.dropdown_cap_seen = 9
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(
        f"/watchlist/{ids['comp']}/listings",
        json={"url": "https://www.booking.com/hotel/vn/comp-renamed.html"},
    )
    assert r.status_code == 201, r.text
    stored = await _reload(db, listing.id)
    assert stored.listing_key == "vn/comp-renamed" and stored.status == "unverified"
    assert (stored.capacity_max, stored.capacity_capped) == (None, False)
    assert (stored.capacity_checked_at, stored.capacity_next_at) == (None, None)
    assert (stored.rooms_max_seen, stored.dropdown_cap_seen) == (None, None)
