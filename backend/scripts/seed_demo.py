"""Nạp dữ liệu demo để chạy dashboard/API cục bộ không cần scrape thật.

Tạo 1 tenant, 1 khách sạn self + 2 đối thủ, 2 người dùng (admin + operator), 6 scan run
trong 2 ngày với snapshot giả có đủ exact/capped/hidden/sold_out, chạy analytics, nạp PMS.

Dùng: cd backend && uv run python scripts/seed_demo.py
Đăng nhập: admin@demo.vn / demo-pass-123 (tenant_admin), op@demo.vn / demo-pass-123 (operator)
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.analytics.service import AnalyticsService
from app.api.auth import hash_password
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Hotel, OwnHotelDaily, ScanRun, Tenant, TenantHotel, User
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus, RatePlan, RoomOffer
from app.repo.snapshots import SnapshotRepository

PASSWORD = "demo-pass-123"
ROOM_TYPES = [
    ("101", "Deluxe Room", 2),
    ("102", "Premier River View", 3),
    ("103", "Executive Suite", 2),
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


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    rng = random.Random(42)
    async with factory() as s:
        if (await s.execute(select(Tenant).where(Tenant.name == "Demo Hotel Group"))).first():
            print("demo data already present")
            return
        tenant = Tenant(
            name="Demo Hotel Group",
            timezone="Asia/Ho_Chi_Minh",
            scan_times=["06:00", "14:00", "22:00"],
            horizon_days=30,
            insight_language="vi",
            insight_hour="07:30",
            country_code="vn",
            active=True,
        )
        hotels = [
            Hotel(
                booking_url="https://www.booking.com/hotel/vn/demo-riverside.html",
                booking_slug="vn/demo-riverside",
                country_code="vn",
                name="Demo Riverside Hotel",
                city="Ho Chi Minh City",
                booking_hotel_id="1000001",
            ),
            Hotel(
                booking_url="https://www.booking.com/hotel/vn/the-reverie-saigon.html",
                booking_slug="vn/the-reverie-saigon",
                country_code="vn",
                name="The Reverie Saigon",
                city="Ho Chi Minh City",
                booking_hotel_id="1000002",
            ),
            Hotel(
                booking_url="https://www.booking.com/hotel/vn/park-hyatt-saigon.html",
                booking_slug="vn/park-hyatt-saigon",
                country_code="vn",
                name="Park Hyatt Saigon",
                city="Ho Chi Minh City",
                booking_hotel_id="1000003",
            ),
        ]
        s.add(tenant)
        s.add_all(hotels)
        await s.flush()
        s.add_all(
            [
                TenantHotel(
                    tenant_id=tenant.id,
                    hotel_id=hotels[0].id,
                    role="self",
                    label="Của tôi",
                    active=True,
                ),
                TenantHotel(
                    tenant_id=tenant.id,
                    hotel_id=hotels[1].id,
                    role="competitor",
                    label="Reverie",
                    active=True,
                ),
                TenantHotel(
                    tenant_id=tenant.id,
                    hotel_id=hotels[2].id,
                    role="competitor",
                    label="Park Hyatt",
                    active=True,
                ),
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
        # trạng thái tồn kho ban đầu theo (hotel, stay_date, room_type)
        stock: dict[tuple[int, int, str], int] = {}
        for h in hotels:
            for d in range(30):
                for rid, _, _ in ROOM_TYPES:
                    stock[(h.id, d, rid)] = rng.choice([1, 2, 3, 4, 6, 8, 12, 15, 20])
        run_ids = []
        for step in range(6):
            at = now - timedelta(hours=8 * (5 - step))
            run = ScanRun(
                trigger_key=f"demo:{step}",
                scheduled_at=at,
                started_at=at,
                finished_at=at + timedelta(minutes=25),
                status="completed",
                total_jobs=3,
            )
            s.add(run)
            await s.flush()
            run_ids.append(run.id)
            for hi, h in enumerate(hotels):
                for d in range(30):
                    stay = today + timedelta(days=d)
                    offers = []
                    for rid, name, occ in ROOM_TYPES:
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
                            offers.append(_offer(rid, name, occ, left, base))
                    if offers:
                        res = ProbeResult(
                            ProbeStatus.OK,
                            ProbeMethod.HTTP,
                            stay,
                            stay + timedelta(days=1),
                            1,
                            2,
                            tuple(offers),
                            "<html/>",
                            200,
                            "demo",
                            900,
                            booking_hotel_id=h.booking_hotel_id,
                            hotel_name=h.name,
                        )
                    else:
                        res = ProbeResult(
                            ProbeStatus.SOLD_OUT,
                            ProbeMethod.HTTP,
                            stay,
                            stay + timedelta(days=1),
                            1,
                            2,
                            (),
                            "<html/>",
                            200,
                            "demo",
                            500,
                        )
                    if rng.random() < 0.03:
                        res = ProbeResult(
                            ProbeStatus.BLOCKED,
                            ProbeMethod.HTTP,
                            stay,
                            stay + timedelta(days=1),
                            1,
                            2,
                            (),
                            None,
                            403,
                            "demo",
                            300,
                            error="blocked",
                        )
                    await repo.write_probe(
                        run.id,
                        h.id,
                        stay,
                        res,
                        None,
                        "1",
                        "vn",
                        at + timedelta(minutes=hi * 5 + d // 3),
                    )
            await s.commit()
            from app.repo.runs import ScanRunRepository

            await ScanRunRepository(s).try_finish_run(run.id, at + timedelta(minutes=25))
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
        print(f"seeded tenant {tenant.id}, hotels {[h.id for h in hotels]}, runs {run_ids}")
        print(
            f"login: admin@demo.vn / {PASSWORD} (tenant_admin), op@demo.vn / {PASSWORD} (operator)"
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
