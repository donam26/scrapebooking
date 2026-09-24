from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.analytics.service import AnalyticsService
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    OwnHotelDaily,
    ScanRun,
    Tenant,
    TenantHotel,
)
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.snapshots import SnapshotRepository

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
STAY = date(2026, 10, 5)


def offer(rid: str, badge: int | None, dropdown: int | None, price: str) -> RoomOffer:
    return RoomOffer(
        rid,
        f"Room {rid}",
        2,
        badge,
        dropdown,
        (RatePlan("Std", Decimal(price), "VND", True, None),),
    )


def result(status: ProbeStatus, *offers: RoomOffer) -> ProbeResult:
    return ProbeResult(
        status,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        offers,
        "<html/>",
        200,
        "s",
        10,
    )


async def _hotel(db: AsyncSession, slug: str) -> int:
    h = Hotel(
        booking_url=f"https://www.booking.com/hotel/{slug}.html",
        booking_slug=slug,
        country_code="vn",
    )
    db.add(h)
    await db.flush()
    return h.id


async def _run(db: AsyncSession, key: str, at: datetime) -> int:
    r = ScanRun(
        trigger_key=key,
        scheduled_at=at,
        started_at=at,
        finished_at=at + timedelta(minutes=30),
        status="completed",
        total_probes=1,
    )
    db.add(r)
    await db.flush()
    return r.id


async def _write(
    db: AsyncSession, run_id: int, hotel_id: int, res: ProbeResult, at: datetime, stay: date = STAY
) -> None:
    await SnapshotRepository(db, page_cap=10).write_probe(
        run_id, hotel_id, stay, res, None, "1", "vn", at
    )


async def test_pipeline_over_three_runs(db: AsyncSession) -> None:
    hotel = await _hotel(db, "vn/a")
    svc = AnalyticsService(db, low_stock_threshold=3, price_change_threshold_pct=3.0)

    run1 = await _run(db, "r1", T0)
    await _write(
        db,
        run1,
        hotel,
        result(ProbeStatus.OK, offer("1", 5, 5, "100"), offer("2", None, 10, "200")),
        T0,
    )
    await db.commit()
    rep1 = await svc.run(run1)
    await db.commit()
    assert (rep1.hotel_dates, rep1.events, rep1.metrics) == (1, 0, 1)
    hds = (await db.execute(select(HotelDateSnapshot))).scalar_one()
    assert hds.status == "available" and hds.exact_rooms_left == 5 and hds.room_types_available == 2
    assert hds.min_price == Decimal("100.00") and hds.room_types_sold_out == 0

    # Run 2, 8 giờ sau: loại 1 còn 2 (giảm 3, vào mức thấp), giá loại 2 tăng 10%.
    run2 = await _run(db, "r2", T0 + timedelta(hours=8))
    await _write(
        db,
        run2,
        hotel,
        result(ProbeStatus.OK, offer("1", 2, 2, "100"), offer("2", None, 10, "220")),
        T0 + timedelta(hours=8),
    )
    await db.commit()
    rep2 = await svc.run(run2)
    await db.commit()
    events = (
        (await db.execute(select(AvailabilityEvent).order_by(AvailabilityEvent.id))).scalars().all()
    )
    types = sorted(e.event_type for e in events)
    assert types == ["low_stock_enter", "price_up", "rooms_decrease"]
    assert rep2.events == 3
    dec = next(e for e in events if e.event_type == "rooms_decrease")
    assert dec.from_value == "5" and dec.to_value == "2" and dec.delta == Decimal("-3.00")
    assert (
        dec.previous_scan_run_id == run1
        and dec.scan_run_id == run2
        and dec.room_type_id is not None
    )

    # Chạy lại run 2: idempotent (không nhân đôi sự kiện).
    await svc.run(run2)
    await db.commit()
    assert len((await db.execute(select(AvailabilityEvent))).scalars().all()) == 3

    # Run 3: bị chặn -> unknown, không sinh sự kiện, metrics giữ status unknown.
    run3 = await _run(db, "r3", T0 + timedelta(hours=16))
    await _write(
        db,
        run3,
        hotel,
        ProbeResult(
            ProbeStatus.BLOCKED,
            ProbeMethod.HTTP,
            STAY,
            STAY + timedelta(days=1),
            1,
            2,
            (),
            None,
            403,
            "s",
            10,
            error="blocked",
        ),
        T0 + timedelta(hours=16),
    )
    await db.commit()
    rep3 = await svc.run(run3)
    await db.commit()
    db.expire_all()
    assert rep3.events == 0
    metric = (await db.execute(select(HotelDateMetric))).scalar_one()
    assert metric.availability_status == "unknown" and metric.as_of_scan_run_id == run3

    # Run 4, ngày hôm sau: hết phòng. So với lần dùng được gần nhất (run 2), không phải run 3.
    run4 = await _run(db, "r4", T0 + timedelta(days=1))
    await _write(db, run4, hotel, result(ProbeStatus.SOLD_OUT), T0 + timedelta(days=1))
    await db.commit()
    rep4 = await svc.run(run4)
    await db.commit()
    db.expire_all()  # metrics được upsert bằng Core insert, buộc ORM đọc lại
    assert rep4.events == 1
    so = (
        await db.execute(
            select(AvailabilityEvent).where(AvailabilityEvent.event_type == "sold_out")
        )
    ).scalar_one()
    assert so.previous_scan_run_id == run2
    metric = (await db.execute(select(HotelDateMetric))).scalar_one()
    assert metric.availability_status == "sold_out" and metric.sold_out_at == T0 + timedelta(days=1)
    assert metric.pickup_24h == 5  # mốc 24h trước = run1 (exact 5) -> hết phòng
    hds4 = (
        await db.execute(select(HotelDateSnapshot).where(HotelDateSnapshot.scan_run_id == run4))
    ).scalar_one()
    assert hds4.room_types_sold_out == 2

    assert await svc.pending_run_ids() == []


async def test_pending_run_ids_lists_unanalyzed_finished_runs(db: AsyncSession) -> None:
    hotel = await _hotel(db, "vn/b")
    run1 = await _run(db, "p1", T0)
    await _write(db, run1, hotel, result(ProbeStatus.OK, offer("1", 1, 1, "100")), T0)
    await db.commit()
    svc = AnalyticsService(db)
    assert await svc.pending_run_ids() == [run1]
    await svc.run(run1)
    await db.commit()
    assert await svc.pending_run_ids() == []


async def test_compset_by_day(db: AsyncSession) -> None:
    tenant = Tenant(
        name="T",
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        active=True,
    )
    db.add(tenant)
    await db.flush()
    own = await _hotel(db, "vn/own")
    c1 = await _hotel(db, "vn/c1")
    c2 = await _hotel(db, "vn/c2")
    c3 = await _hotel(db, "vn/c3")
    db.add_all(
        [
            TenantHotel(tenant_id=tenant.id, hotel_id=own, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c1, role="competitor", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c2, role="competitor", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c3, role="competitor", active=True),
        ]
    )
    run = await _run(db, "c", T0)
    await _write(db, run, own, result(ProbeStatus.OK, offer("1", None, 10, "150")), T0)
    await _write(db, run, c1, result(ProbeStatus.OK, offer("1", None, 10, "100")), T0)
    await _write(db, run, c2, result(ProbeStatus.OK, offer("1", 2, 2, "200")), T0)
    await _write(db, run, c3, result(ProbeStatus.SOLD_OUT), T0)
    db.add(
        OwnHotelDaily(
            tenant_id=tenant.id,
            hotel_id=own,
            stay_date=STAY,
            rooms_total=50,
            rooms_sold=40,
            rooms_available=10,
            occupancy_pct=Decimal("80"),
            source="csv",
            imported_at=T0,
        )
    )
    await db.commit()
    await AnalyticsService(db).run(run)
    await db.commit()

    days = await compset_by_day(db, tenant.id, STAY, STAY + timedelta(days=1))
    assert len(days) == 2
    d = days[0]
    assert d.competitors_observed == 3 and d.competitors_sold_out == 1
    assert d.sold_out_share == Decimal("0.33")
    assert d.min_price == Decimal("100.00") and d.median_price == Decimal("150.00")
    assert d.own_min_price == Decimal("150.00") and d.own_occupancy_pct == Decimal("80.00")
    assert d.price_index == Decimal("100.0")
    assert days[1].competitors_observed == 0 and days[1].median_price is None
