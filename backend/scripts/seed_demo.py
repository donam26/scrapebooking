"""Nạp dữ liệu demo để chạy dashboard/API cục bộ không cần scrape thật.

Tạo 1 tenant, 1 khách sạn self + 2 đối thủ (mỗi khách sạn một listing Booking), 3 người dùng
(admin, viewer, operator), 6 scan run Booking trong 2 ngày với snapshot giả có đủ
exact/capped/hidden/sold_out, chạy analytics, nạp PMS.

Dùng: cd backend && uv run python scripts/seed_demo.py
Đăng nhập: admin@demo.vn / demo-pass-123 (tenant_admin), op@demo.vn / demo-pass-123 (operator)
"""

import asyncio
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.service import AnalyticsService
from app.api.auth import hash_password
from app.collector.booking.selectors import PARSER_VERSION as BOOKING_PARSER_VERSION
from app.config import Settings, get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Hotel, Listing, OwnHotelDaily, Tenant, TenantHotel, User
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.repo.snapshots import SnapshotRepository

PASSWORD = "demo-pass-123"
TENANT_NAME = "Demo Hotel Group"
CHANNEL = "booking"
ROOM_TYPES = [
    ("101", "Deluxe Room", 2),
    ("102", "Premier River View", 3),
    ("103", "Executive Suite", 2),
]
# (slug Booking, id kênh, tên, nhãn watchlist, vai trò)
HOTELS = [
    ("vn/demo-riverside", "1000001", "Demo Riverside Hotel", "Của tôi", "self"),
    ("vn/the-reverie-saigon", "1000002", "The Reverie Saigon", "Reverie", "competitor"),
    ("vn/park-hyatt-saigon", "1000003", "Park Hyatt Saigon", "Park Hyatt", "competitor"),
]


def _offer(rid: str, name: str, occ: int, rooms_left: int, base_price: int) -> RoomOffer:
    if rooms_left <= 0:
        raise ValueError
    if rooms_left <= 5:
        badge, dropdown = rooms_left, rooms_left
    elif rooms_left >= 10:
        badge, dropdown = None, 10
    else:
        badge, dropdown = None, rooms_left
    rates = (
        RatePlan("Non-refundable", Decimal(base_price), "VND", False, None),
        RatePlan("Free cancellation", Decimal(int(base_price * 1.12)), "VND", True, None),
    )
    return RoomOffer(rid, name, occ, badge, dropdown, rates)


def _probe(
    stay_date: date, status: ProbeStatus, offers: tuple[RoomOffer, ...], external_id: str, name: str
) -> ProbeResult:
    if status == ProbeStatus.BLOCKED:
        return ProbeResult(
            status,
            ProbeMethod.HTTP,
            stay_date,
            stay_date + timedelta(days=1),
            1,
            2,
            (),
            None,
            403,
            "demo",
            300,
            error="blocked",
        )
    return ProbeResult(
        status,
        ProbeMethod.HTTP,
        stay_date,
        stay_date + timedelta(days=1),
        1,
        2,
        offers,
        "<html/>",
        200,
        "demo",
        900 if offers else 500,
        external_id=external_id,
        hotel_name=name,
    )


async def seed(s: AsyncSession, settings: Settings, *, seed_value: int = 42) -> dict[str, object]:
    """Ghi dữ liệu demo vào session `s` (commit bên trong). Trả về id đã tạo để kiểm tra."""
    rng = random.Random(seed_value)
    if (await s.execute(select(Tenant).where(Tenant.name == TENANT_NAME))).first():
        return {"skipped": True}
    tenant = Tenant(
        name=TENANT_NAME,
        timezone="Asia/Ho_Chi_Minh",
        scan_times=["06:00", "14:00", "22:00"],
        horizon_days=30,
        insight_language="vi",
        insight_hour="07:30",
        country_code="vn",
        reference_channel=CHANNEL,
        active=True,
    )
    s.add(tenant)
    hotels: list[Hotel] = []
    for _slug, _ext, name, _label, _role in HOTELS:
        hotel = Hotel(name=name, city="Ho Chi Minh City", country_code="vn")
        s.add(hotel)
        hotels.append(hotel)
    await s.flush()
    for hotel, (slug, ext, name, label, role) in zip(hotels, HOTELS, strict=True):
        s.add(
            Listing(
                hotel_id=hotel.id,
                channel=CHANNEL,
                listing_key=slug,
                external_id=ext,
                url=f"https://www.booking.com/hotel/{slug}.html",
                name=name,
                status="active",
                verified_at=datetime.now(tz=UTC),
            )
        )
        s.add(
            TenantHotel(tenant_id=tenant.id, hotel_id=hotel.id, role=role, label=label, active=True)
        )
    s.add_all(
        [
            User(
                tenant_id=tenant.id,
                email="admin@demo.vn",
                password_hash=hash_password(PASSWORD),
                role="tenant_admin",
                active=True,
            ),
            User(
                tenant_id=tenant.id,
                email="viewer@demo.vn",
                password_hash=hash_password(PASSWORD),
                role="viewer",
                active=True,
            ),
            User(
                tenant_id=None,
                email="op@demo.vn",
                password_hash=hash_password(PASSWORD),
                role="operator",
                active=True,
            ),
        ]
    )
    await s.flush()

    now = datetime.now(tz=UTC).replace(minute=0, second=0, microsecond=0)
    today = now.date()
    repo = SnapshotRepository(s, settings.page_dropdown_cap)
    parser_version = f"{CHANNEL}:{BOOKING_PARSER_VERSION}"
    # trạng thái tồn kho ban đầu theo (hotel, stay_date, room_type)
    stock: dict[tuple[int, int, str], int] = {}
    for h in hotels:
        for d in range(30):
            for rid, _, _ in ROOM_TYPES:
                stock[(h.id, d, rid)] = rng.choice([1, 2, 3, 4, 6, 8, 12, 15, 20])
    run_ids: list[int] = []
    runs = ScanRunRepository(s)
    for step in range(6):
        at = now - timedelta(hours=8 * (5 - step))
        run = await runs.create_run(
            f"demo:{step}",
            at,
            [HotelJobPlan(h.id, today, 30) for h in hotels],
            channel=CHANNEL,
        )
        if run is None:
            raise RuntimeError(f"run demo:{step} already exists")
        run_ids.append(run.id)
        for hi, (h, (_slug, ext, name, _label, _role)) in enumerate(
            zip(hotels, HOTELS, strict=True)
        ):
            for d in range(30):
                stay = today + timedelta(days=d)
                offers = []
                for rid, rname, occ in ROOM_TYPES:
                    key = (h.id, d, rid)
                    # bán bớt phòng ngẫu nhiên, ngày gần bán nhanh hơn
                    if rng.random() < (0.35 if d < 10 else 0.15):
                        stock[key] = max(0, stock[key] - rng.choice([1, 1, 2]))
                    left = stock[key]
                    if left > 0:
                        base = 2_000_000 + hi * 900_000 + int(rid[-1]) * 700_000
                        base += (300_000 if stay.weekday() >= 4 else 0) + rng.choice(
                            [-100_000, 0, 0, 150_000]
                        )
                        offers.append(_offer(rid, rname, occ, left, base))
                if rng.random() < 0.03:
                    res = _probe(stay, ProbeStatus.BLOCKED, (), ext, name)
                elif offers:
                    res = _probe(stay, ProbeStatus.OK, tuple(offers), ext, name)
                else:
                    res = _probe(stay, ProbeStatus.SOLD_OUT, (), ext, name)
                await repo.write_probe(
                    run.id,
                    h.id,
                    CHANNEL,
                    stay,
                    res,
                    None,
                    parser_version,
                    "vn",
                    at + timedelta(minutes=hi * 5 + d // 3),
                )
            # job của khách sạn xong: try_finish_run chỉ chốt run khi không còn job dở
            await runs.finish_job(run.id, h.id, "done", at + timedelta(minutes=20))
        await s.commit()
        await runs.try_finish_run(run.id, at + timedelta(minutes=25))
        await s.commit()
    for rid in run_ids:
        await AnalyticsService(
            s, settings.low_stock_threshold, settings.price_change_threshold_pct
        ).run(rid)
        await s.commit()
    for d in range(30):
        stay = today + timedelta(days=d)
        total, sold = 120, rng.randint(50, 118)
        s.add(
            OwnHotelDaily(
                tenant_id=tenant.id,
                hotel_id=hotels[0].id,
                stay_date=stay,
                rooms_total=total,
                rooms_sold=sold,
                rooms_available=total - sold,
                occupancy_pct=Decimal(sold * 100 / total).quantize(Decimal("0.01")),
                adr=Decimal(rng.randint(1_800_000, 2_600_000)),
                revenue=None,
                source="csv",
                imported_at=now,
            )
        )
    await s.commit()
    return {
        "skipped": False,
        "tenant_id": tenant.id,
        "hotel_ids": [h.id for h in hotels],
        "run_ids": run_ids,
    }


async def main(session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    settings = get_settings()
    engine = None
    if session_factory is None:
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
    async with session_factory() as s:
        result = await seed(s, settings)
    if result.get("skipped"):
        print("demo data already present")
    else:
        print(
            f"seeded tenant {result['tenant_id']}, hotels {result['hotel_ids']}, "
            f"runs {result['run_ids']}"
        )
        print(
            f"login: admin@demo.vn / {PASSWORD} (tenant_admin), op@demo.vn / {PASSWORD} (operator)"
        )
    if engine is not None:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
