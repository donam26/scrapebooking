from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, RoomType, ScanRun
from app.domain.models import (
    CalendarDay,
    CalendarResult,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)
from app.repo.snapshots import SnapshotRepository

NOW = datetime(2026, 9, 24, 6, 5, tzinfo=UTC)


async def _seed(db: AsyncSession) -> tuple[int, int]:
    hotel = Hotel(
        booking_url="https://www.booking.com/hotel/vn/x.html",
        booking_slug="vn/x",
        country_code="vn",
    )
    run = ScanRun(trigger_key="2026-09-24T06:00", scheduled_at=NOW, status="running")
    db.add_all([hotel, run])
    await db.flush()
    return hotel.id, run.id


def _result(*offers: RoomOffer, status: ProbeStatus = ProbeStatus.OK) -> ProbeResult:
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
        booking_hotel_id="777",
        hotel_name="Hotel X",
    )


OFFER_A = RoomOffer(
    "101",
    "Deluxe",
    2,
    2,
    2,
    (
        RatePlan("Non-refundable", Decimal("900000"), "VND", False, None),
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

    types = (await db.execute(select(RoomType).order_by(RoomType.booking_room_id))).scalars().all()
    assert [t.booking_room_id for t in types] == ["101", "102"]

    snaps = (
        (await db.execute(select(RoomSnapshot).order_by(RoomSnapshot.room_type_id))).scalars().all()
    )
    assert len(snaps) == 2
    a, b = snaps
    assert a.rooms_left == 2 and a.stock_confidence == "exact" and a.badge_count == 2
    assert a.min_price == Decimal("900000.00") and a.min_refundable_price == Decimal("1000000.00")
    assert a.currency == "VND" and len(a.rates) == 2
    assert b.rooms_left == 10 and b.stock_confidence == "capped" and b.min_refundable_price is None

    hotel = (await db.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
    assert hotel.booking_hotel_id == "777" and hotel.name == "Hotel X"


async def test_write_probe_is_idempotent_per_run_hotel_date(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    p1 = await repo.write_probe(
        run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), "k1", "1", "vn", NOW
    )
    p2 = await repo.write_probe(
        run_id,
        hotel_id,
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
        run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
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
        run_id, hotel_id, date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
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
        run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW
    )
    await repo.write_probe(
        run_id,
        hotel_id,
        date(2026, 10, 6),
        _result(status=ProbeStatus.BLOCKED),
        None,
        "1",
        "vn",
        NOW,
    )
    await repo.write_skipped(
        run_id, hotel_id, date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW
    )
    await db.commit()
    done = await repo.terminal_dates(run_id, hotel_id)
    assert done == {date(2026, 10, 5), date(2026, 10, 7)}
