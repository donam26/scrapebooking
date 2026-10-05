from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import compset_by_day
from app.analytics.service import AnalyticsService
from app.db.models import (
    AvailabilityEvent,
    HotelDateMetric,
    HotelDateSnapshot,
    OwnHotelDaily,
    Tenant,
    TenantHotel,
)
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.snapshots import SnapshotRepository
from tests.integration.seed import add_hotel, scan_run

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
STAY = date(2026, 10, 5)


def offer(
    rid: str,
    badge: int | None,
    dropdown: int | None,
    price: str,
    *,
    currency: str = "VND",
    refundable: bool | None = True,
    taxes_included: bool | None = None,
) -> RoomOffer:
    return RoomOffer(
        rid,
        f"Room {rid}",
        2,
        badge,
        dropdown,
        (
            RatePlan(
                "Std", Decimal(price), currency, refundable, None, taxes_included=taxes_included
            ),
        ),
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


def blocked() -> ProbeResult:
    return ProbeResult(
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
    )


async def _hotel(db: AsyncSession, slug: str) -> int:
    return (await add_hotel(db, slug, channels=("booking", "agoda"))).id


async def _run(db: AsyncSession, key: str, at: datetime, channel: str = "booking") -> int:
    r = scan_run(f"{key}:{channel}", at, channel=channel, finished_at=at + timedelta(minutes=30))
    r.total_probes = 1
    db.add(r)
    await db.flush()
    return r.id


async def _write(
    db: AsyncSession,
    run_id: int,
    hotel_id: int,
    res: ProbeResult,
    at: datetime,
    stay: date = STAY,
    channel: str = "booking",
) -> None:
    await SnapshotRepository(db, page_cap=10).write_probe(
        run_id, hotel_id, channel, stay, res, None, "1", "vn", at
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
    assert hds.channel == "booking"
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
    assert {e.channel for e in events} == {"booking"}
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

    # Run 3: bị chặn -> unknown, không sinh sự kiện; metrics giữ giá/số phòng của run 2 và đánh
    # dấu cũ từ lúc run 2 quan sát.
    run3 = await _run(db, "r3", T0 + timedelta(hours=16))
    await _write(db, run3, hotel, blocked(), T0 + timedelta(hours=16))
    await db.commit()
    rep3 = await svc.run(run3)
    await db.commit()
    db.expire_all()
    assert rep3.events == 0
    metric = (await db.execute(select(HotelDateMetric))).scalar_one()
    assert metric.availability_status == "unknown" and metric.as_of_scan_run_id == run3
    assert (metric.min_price, metric.currency, metric.exact_rooms_left) == (
        Decimal("100.00"),
        "VND",
        2,
    )
    assert metric.stale_since == T0 + timedelta(hours=8)
    assert metric.last_observed_at == T0 + timedelta(hours=16)

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
    assert metric.min_price is None and metric.stale_since is None  # quan sát dùng được: hết cũ
    hds4 = (
        await db.execute(select(HotelDateSnapshot).where(HotelDateSnapshot.scan_run_id == run4))
    ).scalar_one()
    assert hds4.room_types_sold_out == 2

    assert await svc.pending_run_ids() == []


async def _metric(db: AsyncSession, hotel_id: int, channel: str = "booking") -> HotelDateMetric:
    db.expire_all()  # metrics ghi bằng Core insert, buộc ORM đọc lại
    return (
        await db.execute(
            select(HotelDateMetric).where(
                HotelDateMetric.hotel_id == hotel_id,
                HotelDateMetric.channel == channel,
                HotelDateMetric.stay_date == STAY,
            )
        )
    ).scalar_one()


async def test_blocked_probe_keeps_last_known_price_until_next_usable_run(
    db: AsyncSession,
) -> None:
    hotel = await _hotel(db, "vn/keep")
    a = await _run(db, "a", T0)
    await _write(db, a, hotel, result(ProbeStatus.OK, offer("1", 4, 4, "100")), T0)
    await db.commit()
    await _analyze(db, a)
    m = await _metric(db, hotel)
    assert (m.availability_status, m.min_price, m.stale_since) == (
        "available",
        Decimal("100.00"),
        None,
    )

    # Run B bị chặn: ô heatmap giữ giá/số phòng của A, trạng thái unknown, cũ từ lúc A quan sát.
    b = await _run(db, "b", T0 + timedelta(hours=8))
    await _write(db, b, hotel, blocked(), T0 + timedelta(hours=8))
    await db.commit()
    assert await _analyze(db, b) == 0
    m = await _metric(db, hotel)
    assert m.availability_status == "unknown" and m.as_of_scan_run_id == b
    assert (m.min_price, m.min_refundable_price, m.currency, m.exact_rooms_left) == (
        Decimal("100.00"),
        Decimal("100.00"),
        "VND",
        4,
    )
    assert m.stale_since == T0 and m.last_observed_at == T0 + timedelta(hours=8)

    # Bị chặn lần nữa: vẫn giữ mốc cũ nhất.
    b2 = await _run(db, "b2", T0 + timedelta(hours=16))
    await _write(db, b2, hotel, blocked(), T0 + timedelta(hours=16))
    await db.commit()
    await _analyze(db, b2)
    m = await _metric(db, hotel)
    assert m.stale_since == T0 and m.min_price == Decimal("100.00")

    # Run C dùng được: giá mới, hết cũ; sự kiện so với A (lần dùng được gần nhất).
    c = await _run(db, "c", T0 + timedelta(hours=24))
    await _write(
        db, c, hotel, result(ProbeStatus.OK, offer("1", 2, 2, "120")), T0 + timedelta(hours=24)
    )
    await db.commit()
    await _analyze(db, c)
    m = await _metric(db, hotel)
    assert (m.availability_status, m.min_price, m.exact_rooms_left, m.stale_since) == (
        "available",
        Decimal("120.00"),
        2,
        None,
    )
    assert m.pickup_24h == 2  # mốc 24h = run A (exact 4) -> còn 2
    # So với A: giá 100 -> 120 (mức khách sạn + loại phòng), 4 -> 2 phòng, vào mức thấp (≤ 3).
    types = sorted(e.event_type for e in await _events(db, c))
    assert types == ["low_stock_enter", "price_up", "price_up", "rooms_decrease"]
    assert {e.previous_scan_run_id for e in await _events(db, c)} == {a}


async def test_stale_run_does_not_overwrite_newer_metric(db: AsyncSession) -> None:
    # Hai job analytics chạy lệch thứ tự: run cũ hơn phân tích sau không đè metric của run mới.
    hotel = await _hotel(db, "vn/race")
    old = await _run(db, "old", T0)
    await _write(db, old, hotel, result(ProbeStatus.OK, offer("1", 4, 4, "100")), T0)
    new = await _run(db, "new", T0 + timedelta(hours=8))
    await _write(
        db, new, hotel, result(ProbeStatus.OK, offer("1", 3, 3, "110")), T0 + timedelta(hours=8)
    )
    await db.commit()
    rep_new = await AnalyticsService(db).run(new)
    await db.commit()
    rep_old = await AnalyticsService(db).run(old)
    await db.commit()
    assert (rep_new.metrics, rep_old.metrics) == (1, 0)
    m = await _metric(db, hotel)
    assert m.as_of_scan_run_id == new and m.min_price == Decimal("110.00")


async def test_currency_mismatch_yields_no_price_event(db: AsyncSession) -> None:
    # Proxy trả trang USD: 100 VND -> 5 USD không phải "giảm giá 95%".
    hotel = await _hotel(db, "vn/cur")
    r1 = await _run(db, "r1", T0)
    await _write(db, r1, hotel, result(ProbeStatus.OK, offer("1", None, 10, "100")), T0)
    await db.commit()
    await _analyze(db, r1)
    r2 = await _run(db, "r2", T0 + timedelta(hours=8))
    await _write(
        db,
        r2,
        hotel,
        result(ProbeStatus.OK, offer("1", None, 10, "5", currency="USD")),
        T0 + timedelta(hours=8),
    )
    await db.commit()
    assert await _analyze(db, r2) == 0
    assert await _events(db, r2) == []
    m = await _metric(db, hotel)
    assert (m.min_price, m.currency) == (Decimal("5.00"), "USD")
    # Cùng tiền tệ trở lại (so với lần dùng được gần nhất, là lần USD): vẫn không so.
    r3 = await _run(db, "r3", T0 + timedelta(hours=16))
    await _write(
        db, r3, hotel, result(ProbeStatus.OK, offer("1", None, 10, "100")), T0 + timedelta(hours=16)
    )
    await db.commit()
    assert await _analyze(db, r3) == 0


async def test_days_to_arrival_uses_hotel_local_date(db: AsyncSession) -> None:
    # Mốc 06:00 giờ Việt Nam là 23:00 UTC hôm trước: cùng ngày địa phương với mốc 14:00 (07:00 UTC).
    hotel = await _hotel(db, "vn/tz")  # country_code vn
    early = datetime(2026, 9, 23, 23, 0, tzinfo=UTC)
    r1 = await _run(db, "r1", early)
    await _write(db, r1, hotel, result(ProbeStatus.OK, offer("1", 4, 4, "100")), early)
    await db.commit()
    await _analyze(db, r1)
    assert (await _metric(db, hotel)).days_to_arrival == (STAY - date(2026, 9, 24)).days == 11
    later = datetime(2026, 9, 24, 7, 0, tzinfo=UTC)
    r2 = await _run(db, "r2", later)
    await _write(db, r2, hotel, result(ProbeStatus.OK, offer("1", 4, 4, "100")), later)
    await db.commit()
    await _analyze(db, r2)
    assert (await _metric(db, hotel)).days_to_arrival == 11


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


# ---- đa kênh ----


async def _analyze(db: AsyncSession, run_id: int) -> int:
    rep = await AnalyticsService(db).run(run_id)
    await db.commit()
    return rep.events


async def _events(db: AsyncSession, run_id: int) -> list[AvailabilityEvent]:
    rows = await db.execute(
        select(AvailabilityEvent)
        .where(AvailabilityEvent.scan_run_id == run_id)
        .order_by(AvailabilityEvent.event_type)
    )
    return list(rows.scalars())


async def test_channels_are_analyzed_separately(db: AsyncSession) -> None:
    # Giá/số phòng trên Agoda không phải "lần trước" của Booking: không sinh sự kiện chéo nhầm.
    hotel = await _hotel(db, "vn/a")
    b1 = await _run(db, "b1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", 5, 5, "100")), T0)
    a1 = await _run(db, "a1", T0 + timedelta(hours=1), "agoda")
    await _write(
        db,
        a1,
        hotel,
        result(ProbeStatus.OK, offer("1", 2, 2, "100")),
        T0 + timedelta(hours=1),
        channel="agoda",
    )
    await db.commit()
    assert await _analyze(db, b1) == 0
    assert await _analyze(db, a1) == 0
    db.expire_all()
    metrics = (
        await db.execute(select(HotelDateMetric).order_by(HotelDateMetric.channel))
    ).scalars()
    assert [(m.channel, m.exact_rooms_left) for m in metrics] == [("agoda", 2), ("booking", 5)]


async def test_sold_out_on_one_channel_while_open_elsewhere_is_channel_closed(
    db: AsyncSession,
) -> None:
    hotel = await _hotel(db, "vn/a")
    b1 = await _run(db, "b1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", 2, 2, "100")), T0)
    a1 = await _run(db, "a1", T0, "agoda")
    await _write(
        db, a1, hotel, result(ProbeStatus.OK, offer("1", 3, 3, "100")), T0, channel="agoda"
    )
    await db.commit()
    await _analyze(db, b1)
    await _analyze(db, a1)

    b2 = await _run(db, "b2", T0 + timedelta(hours=8))
    await _write(db, b2, hotel, result(ProbeStatus.SOLD_OUT), T0 + timedelta(hours=8))
    await db.commit()
    await _analyze(db, b2)
    # Agoda chỉ có quan sát của mốc trước (8h): không đem so, chưa kết luận đóng kênh.
    assert [(e.event_type, e.channel) for e in await _events(db, b2)] == [("sold_out", "booking")]

    # Run Agoda cùng mốc chốt sau (30 phút): đánh giá lại, gắn channel_closed cho Booking.
    a2 = await _run(db, "a2", T0 + timedelta(hours=8, minutes=30), "agoda")
    await _write(
        db,
        a2,
        hotel,
        result(ProbeStatus.OK, offer("1", 3, 3, "100")),
        T0 + timedelta(hours=8, minutes=30),
        channel="agoda",
    )
    await db.commit()
    await _analyze(db, a2)
    closed = [e for e in await _events(db, a2) if e.event_type == "channel_closed"]
    assert [(e.channel, e.from_value, e.to_value, e.room_type_id) for e in closed] == [
        ("booking", "agoda", "booking", None)
    ]


async def test_channel_closed_fires_once_while_still_sold_out(db: AsyncSession) -> None:
    hotel = await _hotel(db, "vn/a")
    b1 = await _run(db, "b1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", 2, 2, "100")), T0)
    a1 = await _run(db, "a1", T0, "agoda")
    await _write(
        db, a1, hotel, result(ProbeStatus.OK, offer("1", 3, 3, "100")), T0, channel="agoda"
    )
    await db.commit()
    await _analyze(db, b1)
    await _analyze(db, a1)

    async def slot(key: str, at: datetime) -> list[AvailabilityEvent]:
        b = await _run(db, f"{key}b", at)
        await _write(db, b, hotel, result(ProbeStatus.SOLD_OUT), at)
        await db.commit()
        await _analyze(db, b)
        a = await _run(db, f"{key}a", at + timedelta(minutes=30), "agoda")
        await _write(
            db,
            a,
            hotel,
            result(ProbeStatus.OK, offer("1", 3, 3, "100")),
            at + timedelta(minutes=30),
            channel="agoda",
        )
        await db.commit()
        await _analyze(db, a)
        return [e for e in await _events(db, a) if e.event_type == "channel_closed"]

    # Mốc 1: Booking vừa hết, Agoda còn bán -> channel_closed.
    assert [(e.channel, e.to_value) for e in await slot("s1", T0 + timedelta(hours=8))] == [
        ("booking", "booking")
    ]
    # Mốc sau, quá 24h: Booking *vẫn* hết (không có sold_out mới) -> không báo lại.
    assert await slot("s2", T0 + timedelta(hours=33)) == []
    closed = (
        await db.execute(
            select(AvailabilityEvent).where(AvailabilityEvent.event_type == "channel_closed")
        )
    ).scalars()
    assert len(list(closed)) == 1


async def test_sold_out_everywhere_is_not_channel_closed(db: AsyncSession) -> None:
    hotel = await _hotel(db, "vn/a")
    b1 = await _run(db, "b1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", 2, 2, "100")), T0)
    a1 = await _run(db, "a1", T0 + timedelta(hours=7), "agoda")
    await _write(
        db, a1, hotel, result(ProbeStatus.SOLD_OUT), T0 + timedelta(hours=7), channel="agoda"
    )
    await db.commit()
    await _analyze(db, b1)
    await _analyze(db, a1)
    b2 = await _run(db, "b2", T0 + timedelta(hours=8))
    await _write(db, b2, hotel, result(ProbeStatus.SOLD_OUT), T0 + timedelta(hours=8))
    await db.commit()
    await _analyze(db, b2)
    assert [e.event_type for e in await _events(db, b2)] == ["sold_out"]


async def test_parity_gap_once_per_24h(db: AsyncSession) -> None:
    hotel = await _hotel(db, "vn/a")
    # Parity chỉ sinh cho khách sạn mà một tenant theo dõi là "của bạn".
    tenant = Tenant(name="P", timezone="Asia/Ho_Chi_Minh", country_code="vn", active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantHotel(tenant_id=tenant.id, hotel_id=hotel, role="self", active=True))
    await db.flush()
    b1 = await _run(db, "b1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", None, 10, "1000")), T0)
    await db.commit()
    await _analyze(db, b1)

    async def agoda_run(key: str, at: datetime, price: str) -> int:
        run = await _run(db, key, at, "agoda")
        await _write(
            db, run, hotel, result(ProbeStatus.OK, offer("1", None, 10, price)), at, channel="agoda"
        )
        await db.commit()
        await _analyze(db, run)
        return run

    a1 = await agoda_run("a1", T0 + timedelta(hours=1), "900")
    [gap] = await _events(db, a1)
    assert (gap.event_type, gap.channel, gap.from_value, gap.to_value, gap.delta) == (
        "parity_gap",
        "agoda",
        "booking:1000.00",
        "900.00",
        Decimal("-10.00"),
    )
    # Lượt sau trong 24h: không báo lặp lại; quá 24h thì báo lại nếu vẫn lệch.
    a2 = await agoda_run("a2", T0 + timedelta(hours=9), "900")
    assert [e.event_type for e in await _events(db, a2)] == []
    # Booking cũ quá 12h không còn đem so được: đặt lại Booking mới cho lượt thứ ba.
    b2 = await _run(db, "b2", T0 + timedelta(hours=26))
    await _write(
        db,
        b2,
        hotel,
        result(ProbeStatus.OK, offer("1", None, 10, "1000")),
        T0 + timedelta(hours=26),
    )
    await db.commit()
    await _analyze(db, b2)
    a3 = await agoda_run("a3", T0 + timedelta(hours=27), "900")
    assert [e.event_type for e in await _events(db, a3)] == ["parity_gap"]


async def test_parity_gap_requires_comparable_price_basis(db: AsyncSession) -> None:
    """Không có gói huỷ miễn phí ở cả hai kênh và một kênh không rõ đã gồm thuế: không so giá
    thấp nhất (giá chưa thuế rẻ hơn 20% không phải parity gap)."""
    hotel = await _hotel(db, "vn/basis")
    tenant = Tenant(name="P", timezone="Asia/Ho_Chi_Minh", country_code="vn", active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantHotel(tenant_id=tenant.id, hotel_id=hotel, role="self", active=True))
    await db.flush()

    async def pair(key: str, at: datetime, booking_tax: bool | None) -> list[str]:
        b = await _run(db, f"{key}b", at)
        await _write(
            db,
            b,
            hotel,
            result(
                ProbeStatus.OK,
                offer("1", None, 10, "1000", refundable=False, taxes_included=booking_tax),
            ),
            at,
        )
        await db.commit()
        await _analyze(db, b)
        a = await _run(db, f"{key}a", at + timedelta(minutes=5), "agoda")
        await _write(
            db,
            a,
            hotel,
            result(
                ProbeStatus.OK, offer("1", None, 10, "800", refundable=False, taxes_included=True)
            ),
            at + timedelta(minutes=5),
            channel="agoda",
        )
        await db.commit()
        await _analyze(db, a)
        return [e.event_type for e in await _events(db, a)]

    assert "parity_gap" not in await pair("p1", T0, None)
    assert "parity_gap" not in await pair("p2", T0 + timedelta(hours=8), False)
    # Cả hai lần quan sát đã gồm thuế: so được.
    assert await pair("p3", T0 + timedelta(hours=16), True) == ["parity_gap"]


async def test_compset_by_day_stale_prices_currency_and_multi_self(db: AsyncSession) -> None:
    tenant = Tenant(name="T", timezone="Asia/Ho_Chi_Minh", country_code="vn", active=True)
    db.add(tenant)
    await db.flush()
    own = await _hotel(db, "vn/own")  # id nhỏ nhất -> khách sạn self chính
    own2 = await _hotel(db, "vn/own2")
    c1 = await _hotel(db, "vn/c1")
    c2 = await _hotel(db, "vn/c2")
    c3 = await _hotel(db, "vn/c3")
    db.add_all(
        [
            TenantHotel(tenant_id=tenant.id, hotel_id=own, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=own2, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c1, role="competitor", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c2, role="competitor", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=c3, role="competitor", active=True),
        ]
    )
    for hid, occ in ((own, "80"), (own2, "50")):
        db.add(
            OwnHotelDaily(
                tenant_id=tenant.id,
                hotel_id=hid,
                stay_date=STAY,
                rooms_total=50,
                rooms_sold=40,
                rooms_available=10,
                occupancy_pct=Decimal(occ),
                source="csv",
                imported_at=T0,
            )
        )
    # c2 có giá từ 2 ngày trước rồi bị chặn: quá 24h, không đóng góp. c1 có giá 8h trước rồi bị
    # chặn: còn dùng. c3 giá USD: loại khỏi trung vị (dropped_currency).
    old = await _run(db, "old", T0 - timedelta(days=2))
    await _write(
        db, old, c2, result(ProbeStatus.OK, offer("1", None, 10, "200")), T0 - timedelta(days=2)
    )
    r1 = await _run(db, "r1", T0)
    await _write(db, r1, c1, result(ProbeStatus.OK, offer("1", None, 10, "100")), T0)
    r2 = await _run(db, "r2", T0 + timedelta(hours=8))
    at2 = T0 + timedelta(hours=8)
    await _write(db, r2, own, result(ProbeStatus.OK, offer("1", None, 10, "150")), at2)
    await _write(db, r2, own2, result(ProbeStatus.SOLD_OUT), at2)
    await _write(db, r2, c1, blocked(), at2)
    await _write(db, r2, c2, blocked(), at2)
    await _write(db, r2, c3, result(ProbeStatus.OK, offer("1", None, 10, "7", currency="USD")), at2)
    await db.commit()
    for run in (old, r1, r2):
        await _analyze(db, run)
    db.expire_all()  # metrics upsert bằng Core: không đọc bản cũ trong identity map

    [d] = await compset_by_day(db, tenant.id, STAY, STAY)
    assert (d.competitors_observed, d.competitors_sold_out) == (2, 0)  # c1 (giá cũ 8h), c3
    assert (d.min_price, d.median_price, d.currency) == (
        Decimal("100.00"),
        Decimal("100.00"),
        "VND",
    )
    assert d.dropped_currency == 1
    assert (d.own_min_price, d.price_index, d.own_rank, d.priced_hotels) == (
        Decimal("150.00"),
        Decimal("150.0"),
        2,
        2,
    )
    # Khách sạn self chính (id nhỏ nhất) quyết định trạng thái và số liệu PMS.
    assert d.own_status == "available" and d.own_occupancy_pct == Decimal("80.00")


async def test_compset_by_day_reads_one_channel(db: AsyncSession) -> None:
    tenant = Tenant(name="T", timezone="Asia/Ho_Chi_Minh", country_code="vn", active=True)
    db.add(tenant)
    await db.flush()
    own = await _hotel(db, "vn/own")
    comp = await _hotel(db, "vn/c1")
    db.add_all(
        [
            TenantHotel(tenant_id=tenant.id, hotel_id=own, role="self", active=True),
            TenantHotel(tenant_id=tenant.id, hotel_id=comp, role="competitor", active=True),
        ]
    )
    b = await _run(db, "b", T0)
    await _write(db, b, comp, result(ProbeStatus.OK, offer("1", None, 10, "100")), T0)
    a = await _run(db, "a", T0, "agoda")
    await _write(db, a, comp, result(ProbeStatus.SOLD_OUT), T0, channel="agoda")
    await db.commit()
    await _analyze(db, b)
    await _analyze(db, a)
    [booking] = await compset_by_day(db, tenant.id, STAY, STAY)
    [agoda] = await compset_by_day(db, tenant.id, STAY, STAY, channel="agoda")
    assert (booking.competitors_sold_out, booking.min_price) == (0, Decimal("100.00"))
    assert (agoda.competitors_sold_out, agoda.min_price) == (1, None)


async def test_parity_gap_not_emitted_for_competitor_only_hotel(db: AsyncSession) -> None:
    """Giá đối thủ lệch giữa kênh không sinh parity_gap (chỉ khách sạn "của bạn")."""
    hotel = await _hotel(db, "vn/c")
    b1 = await _run(db, "c1", T0)
    await _write(db, b1, hotel, result(ProbeStatus.OK, offer("1", None, 10, "1000")), T0)
    await db.commit()
    await _analyze(db, b1)
    a1 = await _run(db, "c1:agoda", T0 + timedelta(minutes=5), channel="agoda")
    await _write(
        db,
        a1,
        hotel,
        result(ProbeStatus.OK, offer("1", None, 10, "800")),
        T0 + timedelta(minutes=5),
        channel="agoda",
    )
    await db.commit()
    await _analyze(db, a1)
    assert "parity_gap" not in [e.event_type for e in await _events(db, a1)]
