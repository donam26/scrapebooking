from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Hotel,
    HotelCalendar,
    Listing,
    ListingDemandSignal,
    Probe,
    RoomSnapshot,
    RoomType,
)
from app.domain.models import (
    CalendarDay,
    CalendarResult,
    DemandKind,
    DemandSignal,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)
from app.repo.snapshots import SnapshotRepository
from tests.integration.seed import add_hotel, add_listing, scan_run

NOW = datetime(2026, 9, 24, 6, 5, tzinfo=UTC)


async def _seed(db: AsyncSession) -> tuple[int, int]:
    hotel = await add_hotel(db, "vn/x")
    run = scan_run("2026-09-24T06:00:booking", NOW, status="running")
    db.add(run)
    await db.flush()
    return hotel.id, run.id


def _result(
    *offers: RoomOffer,
    status: ProbeStatus = ProbeStatus.OK,
    demand: tuple[DemandSignal, ...] = (),
) -> ProbeResult:
    return ProbeResult(
        status=status,
        method=ProbeMethod.HTTP,
        checkin=date(2026, 10, 5),
        checkout=date(2026, 10, 6),
        nights=1,
        adults=2,
        offers=offers,
        raw_html="<html/>",
        http_status=200,
        session_id="s1",
        duration_ms=120,
        external_id="777",
        hotel_name="Hotel X",
        demand_signals=demand,
    )


OFFER_A = RoomOffer(
    "101",
    "Deluxe",
    2,
    2,
    2,
    (
        RatePlan(
            "Non-refundable",
            Decimal("900000"),
            "VND",
            False,
            None,
            price_original=Decimal("1200000"),
            taxes_included=True,
            promo_label="Getaway Deal",
        ),
        RatePlan("Free cancellation", Decimal("1000000"), "VND", True, None),
    ),
)
OFFER_B = RoomOffer(
    "102", "Suite", 3, None, 10, (RatePlan("Standard", Decimal("2500000"), "VND", None, True),)
)


async def test_write_probe_creates_room_types_and_snapshots(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    probe_id = await repo.write_probe(
        scan_run_id=run_id,
        hotel_id=hotel_id,
        channel="booking",
        stay_date=date(2026, 10, 5),
        result=_result(OFFER_A, OFFER_B),
        raw_object_key="k1",
        parser_version="1",
        proxy_country="vn",
        fetched_at=NOW,
    )
    await db.commit()

    probe = (await db.execute(select(Probe).where(Probe.id == probe_id))).scalar_one()
    assert probe.status == "ok" and probe.raw_object_key == "k1" and probe.method == "http"

    assert probe.channel == "booking"
    types = (await db.execute(select(RoomType).order_by(RoomType.external_room_id))).scalars().all()
    assert [(t.external_room_id, t.channel) for t in types] == [
        ("101", "booking"),
        ("102", "booking"),
    ]

    snaps = (
        (await db.execute(select(RoomSnapshot).order_by(RoomSnapshot.room_type_id))).scalars().all()
    )
    assert len(snaps) == 2
    a, b = snaps
    assert a.rooms_left == 2 and a.stock_confidence == "exact" and a.badge_count == 2
    assert a.min_price == Decimal("900000.00") and a.min_refundable_price == Decimal("1000000.00")
    assert a.currency == "VND" and len(a.rates) == 2
    assert a.channel == "booking" and a.stock_scope == "room_type"
    assert a.rates[0] == {
        "name": "Non-refundable",
        "price": "900000",
        "currency": "VND",
        "refundable": False,
        "breakfast": None,
        "max_persons": None,
        "price_original": "1200000",
        "taxes_included": True,
        "promo_label": "Getaway Deal",
        "source_supplier": None,
    }
    assert b.rooms_left == 10 and b.stock_confidence == "capped" and b.min_refundable_price is None

    # Định danh của kênh ghi vào listing; tên khách sạn (property) lấy từ kênh đầu tiên.
    listing = (await db.execute(select(Listing))).scalar_one()
    assert (listing.external_id, listing.name) == ("777", "Hotel X")
    hotel = (await db.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
    assert hotel.name == "Hotel X"


async def test_write_probe_is_idempotent_per_run_hotel_date(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    p1 = await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(OFFER_A), "k1", "1", "vn", NOW
    )
    p2 = await repo.write_probe(
        run_id,
        hotel_id,
        "booking",
        date(2026, 10, 5),
        _result(OFFER_A, OFFER_B),
        "k2",
        "2",
        "vn",
        NOW + timedelta(minutes=1),
    )
    await db.commit()
    assert p1 == p2
    probes = (await db.execute(select(Probe))).scalars().all()
    assert len(probes) == 1 and probes[0].raw_object_key == "k2" and probes[0].parser_version == "2"
    snaps = (await db.execute(select(RoomSnapshot))).scalars().all()
    assert len(snaps) == 2


async def test_room_type_last_seen_updates(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
        "booking",
        date(2026, 10, 6),
        _result(OFFER_A),
        None,
        "1",
        "vn",
        NOW + timedelta(hours=1),
    )
    await db.commit()
    rt = (await db.execute(select(RoomType))).scalar_one()
    assert rt.first_seen_at == NOW and rt.last_seen_at == NOW + timedelta(hours=1)


async def test_write_skipped_and_sold_out_have_no_snapshots(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_skipped(
        run_id, hotel_id, "booking", date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
        "booking",
        date(2026, 10, 8),
        _result(status=ProbeStatus.SOLD_OUT),
        "k",
        "1",
        "vn",
        NOW,
    )
    await db.commit()
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["skipped_calendar", "sold_out"]
    assert probes[0].method == "calendar"
    assert (await db.execute(select(RoomSnapshot))).scalars().all() == []


async def test_write_calendar_upserts(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    cal = CalendarResult(
        ok=True,
        days=(
            CalendarDay(date(2026, 10, 5), True, 1, "VND 1"),
            CalendarDay(date(2026, 10, 6), False, 1, None),
        ),
    )
    await repo.write_calendar(hotel_id, run_id, cal, fetched_at=NOW)
    await repo.write_calendar(hotel_id, run_id, cal, fetched_at=NOW)
    await db.commit()
    rows = (
        (await db.execute(select(HotelCalendar).order_by(HotelCalendar.stay_date))).scalars().all()
    )
    assert [(r.stay_date, r.available) for r in rows] == [
        (date(2026, 10, 5), True),
        (date(2026, 10, 6), False),
    ]


async def test_terminal_dates_for_run(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
        "booking",
        date(2026, 10, 6),
        _result(status=ProbeStatus.BLOCKED),
        None,
        "1",
        "vn",
        NOW,
    )
    await repo.write_skipped(
        run_id, hotel_id, "booking", date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW
    )
    await db.commit()
    done = await repo.terminal_dates(run_id, hotel_id)
    assert done == {date(2026, 10, 5), date(2026, 10, 7)}


async def test_same_room_id_on_two_channels_is_two_room_types(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    await add_listing(db, hotel_id, "agoda", "agoda-x")
    agoda_run = scan_run("2026-09-24T06:00:agoda", NOW, channel="agoda", status="running")
    db.add(agoda_run)
    await db.flush()
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await repo.write_probe(
        agoda_run.id, hotel_id, "agoda", date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await db.commit()
    rows = (await db.execute(select(RoomType.channel).order_by(RoomType.channel))).scalars()
    assert list(rows) == ["agoda", "booking"]
    listings = (await db.execute(select(Listing.channel, Listing.external_id))).all()
    assert sorted(listings) == [("agoda", "777"), ("booking", "777")]


async def test_existing_hotel_name_is_not_overwritten(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    hotel = (await db.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
    hotel.name = "Caravelle Saigon"
    await db.flush()
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await db.commit()
    db.expire_all()
    assert (await db.get(Hotel, hotel_id)).name == "Caravelle Saigon"  # type: ignore[union-attr]


async def test_rate_scope_stock_is_capped(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    offer = RoomOffer(
        "201",
        "Superior",
        2,
        1,
        None,
        (RatePlan("Standard", Decimal("800000"), "VND", None, None),),
        stock_scope="rate",
    )
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(
        run_id, hotel_id, "booking", date(2026, 10, 5), _result(offer), None, "1", "vn", NOW
    )
    await db.commit()
    snap = (await db.execute(select(RoomSnapshot))).scalar_one()
    assert (snap.rooms_left, snap.stock_confidence, snap.stock_scope) == (1, "capped", "rate")


async def test_demand_signals_one_row_per_run_kind_and_night(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    hotel_wide = DemandSignal(DemandKind.BOOKINGS_24H, Decimal("13"), 24, None, "đặt 13 lần")
    nightly = DemandSignal(DemandKind.HIGH_DEMAND, Decimal("1"), None, date(2026, 10, 5))
    repo = SnapshotRepository(db, page_cap=10)
    for stay in (date(2026, 10, 5), date(2026, 10, 6)):
        await repo.write_probe(
            run_id,
            hotel_id,
            "booking",
            stay,
            _result(OFFER_A, demand=(hotel_wide, nightly)),
            None,
            "1",
            "vn",
            NOW,
        )
    await db.commit()
    rows = (
        await db.execute(
            select(
                ListingDemandSignal.kind,
                ListingDemandSignal.stay_date,
                ListingDemandSignal.value,
                ListingDemandSignal.window_hours,
                ListingDemandSignal.raw_text,
            ).order_by(ListingDemandSignal.kind)
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("bookings_24h", None, Decimal("13.000"), 24, "đặt 13 lần"),
        ("high_demand", date(2026, 10, 5), Decimal("1.000"), None, None),
    ]


async def test_mark_listing_broken(db: AsyncSession) -> None:
    hotel_id, _ = await _seed(db)
    await SnapshotRepository(db, page_cap=10).mark_listing_broken(hotel_id, "booking", "http 404")
    await db.commit()
    listing = (await db.execute(select(Listing))).scalar_one()
    assert (listing.status, listing.last_error) == ("broken", "http 404")


async def test_last_usable_probe_at_per_channel(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    d1, d2, d3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
    await repo.write_probe(run_id, hotel_id, "booking", d1, _result(OFFER_A), None, "1", "vn", NOW)
    await repo.write_probe(
        run_id, hotel_id, "booking", d2, _result(status=ProbeStatus.BLOCKED), None, "1", "vn", NOW
    )
    await repo.write_skipped(run_id, hotel_id, "booking", d3, nights=1, adults=2, fetched_at=NOW)
    await db.commit()
    assert await repo.last_usable_probe_at(hotel_id, "booking", [d1, d2, d3]) == {
        d1: NOW,
        d3: NOW,
    }  # bị chặn không phải quan sát dùng được
    assert await repo.last_usable_probe_at(hotel_id, "agoda", [d1, d2, d3]) == {}
    assert await repo.last_usable_probe_at(hotel_id, "booking", []) == {}
