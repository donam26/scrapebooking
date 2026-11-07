"""Tenant demo cho video giới thiệu OTARadar: khách sạn tên giả, dữ liệu minh hoạ.

Chỉ chạy trên database riêng có tên kết thúc bằng `_demo` (mặc định `scrapebooking_demo`), không
bao giờ trên database dev chứa tenant 9 (dữ liệu Booking.com thật). Không có worker nào trỏ vào
database này nên các URL giả không bao giờ bị quét.

Dữ liệu đi qua đúng pipeline thật: một collector kịch bản thay Booking.com, `run_probe_hotel` của
worker ghi probe/lịch/thang phòng, `AnalyticsService` tính sự kiện và chỉ số, `OccupancyService`
tính chỉ báo lấp đầy. Gợi ý giá, "Việc cần làm hôm nay", lịch giá... do API tự tính như dữ liệu thật.

Kịch bản (theo `plans/reports/video-script-261024-1107-otaradar-product-video.md`):
- 7 khách sạn 4 sao giả ở Đà Nẵng (của bạn + 6 đối thủ), quét 06:00/14:00/22:00 trong 14 ngày qua tới mốc gần nhất.
- Thứ Bảy đầu tiên cách hôm nay ≥ 5 ngày: 2 đối thủ hết phòng dần, 2 còn ≤ 3 phòng, đối thủ tăng
  giá; khách sạn của bạn giữ giá → gợi ý tăng giá có lý do ("4/6 đối thủ hết/sắp hết phòng").
- Tối nay: 2/6 đối thủ hết phòng (việc "Đối thủ hết phòng" trên Hôm nay).
- Một hội nghị (sự kiện địa phương) sau 17 ngày; OTB từ PMS 30 đêm tới.
- Khu vực thị trường bán kính 3 km với ~45 khách sạn giả, quét 14 đêm.

Dùng (từ thư mục gốc repo): `make demo-video-db` — tạo lại database, migrate, nạp dữ liệu.
Chạy lại ngay trước khi quay: dữ liệu cũ hơn 10 giờ (một chu kỳ quét) thì app tạm dừng gợi ý giá.
Đăng nhập: demo@otaradar.vn / otaradar-demo-2026 (tenant_admin).
"""

import asyncio
import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.engine import make_url

from app.analytics.service import AnalyticsService
from app.api.auth import hash_password
from app.clock import FixedClock
from app.collector.storage import MemoryRawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Hotel, Listing, OwnHotelDaily, Tenant, TenantHotel, User
from app.db.partitions import ensure_room_snapshot_partitions
from app.domain.models import (
    CalendarDay,
    CalendarResult,
    ListingRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)
from app.market.models import LocalEvent
from app.market.occupancy_service import OccupancyService
from app.marketscan.city import area_scope
from app.marketscan.models import MarketArea, MarketListScan
from app.marketscan.parser import SearchCard
from app.marketscan.upsert import record_page, record_rung
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.worker.jobs import WorkerDeps, run_probe_hotel

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SCAN_TIMES = (time(6), time(14), time(22))
HISTORY_DAYS = 14
HORIZON_DAYS = 90
TENANT_NAME = "Sao Mai Riverside (demo video)"
EMAIL = "demo@otaradar.vn"
PASSWORD = "otaradar-demo-2026"
CENTER = (16.0610, 108.2290)  # Đà Nẵng, bên sông Hàn
ROOM_TYPES = (  # (mã, tên, tỷ lệ phòng giao Booking, hệ số giá)
    ("superior", "Superior Double Room", 0.45, 1.0),
    ("deluxe", "Deluxe City View", 0.35, 1.18),
    ("suite", "Ocean View Suite", 0.20, 1.55),
)


@dataclass(frozen=True)
class DemoHotel:
    key: str
    name: str
    role: str  # self | competitor
    label: str
    rooms_total: int  # số phòng công bố
    allotment: int  # phòng giao Booking.com mỗi đêm
    popularity: float  # hệ số lấp đầy so với cầu chung
    base_price: int  # VND/đêm ngày thường, hạng rẻ nhất
    # Mức lấp đầy phần phòng Booking ở lượt quét cuối cho hai đêm của cốt truyện (≥ 1 = hết phòng;
    # phòng còn = allotment × (1 − mức)): tối nay và thứ Bảy của video.
    tonight_fill: float
    hero_fill: float
    lat: float
    lng: float
    review: str
    promo: str | None = None

    @property
    def dynamic(self) -> bool:
        """Đối thủ đổi giá theo cầu; khách sạn của bạn giữ giá (cốt truyện video)."""
        return self.role == "competitor"


HOTELS = (
    DemoHotel(
        "sao-mai-riverside",
        "Sao Mai Riverside Hotel",
        "self",
        "Của tôi",
        rooms_total=120,
        allotment=22,
        popularity=0.85,
        base_price=1_450_000,
        tonight_fill=0.76,
        hero_fill=0.80,
        lat=16.0614,
        lng=108.2286,
        review="8.6",
    ),
    DemoHotel(
        "hoa-ban-boutique",
        "Hoa Ban Boutique Hotel",
        "competitor",
        "Hoa Ban",
        rooms_total=80,
        allotment=14,
        popularity=1.10,
        base_price=1_650_000,
        tonight_fill=1.05,
        hero_fill=1.05,
        lat=16.0652,
        lng=108.2301,
        review="8.9",
    ),
    DemoHotel(
        "thien-thanh-grand",
        "Thiên Thanh Grand Hotel",
        "competitor",
        "Thiên Thanh",
        rooms_total=150,
        allotment=24,
        popularity=0.95,
        base_price=1_850_000,
        tonight_fill=0.72,
        hero_fill=0.90,
        lat=16.0578,
        lng=108.2334,
        review="8.4",
        promo="Getaway Deal",
    ),
    DemoHotel(
        "lam-son-central",
        "Lam Sơn Central Hotel",
        "competitor",
        "Lam Sơn",
        rooms_total=100,
        allotment=16,
        popularity=1.05,
        base_price=1_550_000,
        tonight_fill=1.04,
        hero_fill=1.03,
        lat=16.0689,
        lng=108.2247,
        review="8.2",
    ),
    DemoHotel(
        "ngoc-lan-ocean-view",
        "Ngọc Lan Ocean View",
        "competitor",
        "Ngọc Lan",
        rooms_total=110,
        allotment=18,
        popularity=0.95,
        base_price=1_750_000,
        tonight_fill=0.74,
        hero_fill=0.86,
        lat=16.0631,
        lng=108.2405,
        review="8.7",
    ),
    DemoHotel(
        "moc-mien-spa",
        "Mộc Miên Hotel & Spa",
        "competitor",
        "Mộc Miên",
        rooms_total=90,
        allotment=15,
        popularity=0.90,
        base_price=1_600_000,
        tonight_fill=0.70,
        hero_fill=0.70,
        lat=16.0597,
        lng=108.2262,
        review="8.5",
    ),
    DemoHotel(
        "truc-xanh-boutique",
        "Trúc Xanh Boutique",
        "competitor",
        "Trúc Xanh",
        rooms_total=70,
        allotment=12,
        popularity=0.92,
        base_price=1_500_000,
        tonight_fill=0.68,
        hero_fill=0.62,
        lat=16.0668,
        lng=108.2359,
        review="8.3",
    ),
)


def _noise(*parts: object) -> float:
    """Số giả ngẫu nhiên ổn định trong [0, 1) theo khoá: cùng khoá cho cùng kết quả mọi lượt."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _round_price(v: float) -> int:
    return int(round(v / 10_000) * 10_000)


class Scenario:
    """Cầu, phòng còn và giá theo (khách sạn, đêm, thời điểm quan sát).

    Đêm thường: lấp đầy = cầu chung × độ hút khách × đường cong đặt sớm (càng gần ngày càng đầy).
    Tối nay và thứ Bảy của video: đạt đúng `tonight_fill`/`hero_fill` ở lượt quét cuối và thấp hơn
    ở các lượt trước, nên đối thủ hết phòng dần trong vài ngày qua (có sự kiện "hết phòng").
    """

    def __init__(self, today: date, final_at: datetime) -> None:
        self.today = today
        self.final_at = final_at
        # Thứ Bảy của video: cách hôm nay 5–11 ngày, đủ xa để có lịch sử hết phòng dần.
        self.hero = today + timedelta(days=5 + (5 - (today + timedelta(days=5)).weekday()) % 7)
        self.event = (today + timedelta(days=17), today + timedelta(days=18))

    @staticmethod
    def _curve(d: date, at: datetime) -> float:
        lead = (datetime.combine(d, time(14), TZ) - at.astimezone(TZ)).total_seconds() / 86400
        return 1 / (1 + (max(lead, 0) / 10) ** 1.3)

    def demand(self, d: date) -> float:
        """Cầu chung của khu vực cho đêm `d` (≈ mức lấp đầy sát ngày của khách sạn trung bình)."""
        if d == self.today:
            return 0.97
        if d == self.hero:
            return 1.75
        if d in self.event:
            base = 1.25
        else:
            base = {4: 0.74, 5: 0.82}.get(d.weekday(), 0.56)
        return base + (_noise("demand", d) - 0.5) * 0.12

    def fill(self, h: DemoHotel, d: date, at: datetime) -> float:
        target = {self.today: h.tonight_fill, self.hero: h.hero_fill}.get(d)
        if target is not None:
            return target * self._curve(d, at) / self._curve(d, self.final_at)
        return self.demand(d) * h.popularity * self._curve(d, at)

    def rooms_left(self, h: DemoHotel, d: date, at: datetime) -> int:
        return max(0, h.allotment - int(h.allotment * min(self.fill(h, d, at), 1.0)))

    def price(self, h: DemoHotel, d: date, at: datetime) -> int:
        # Khách sạn của bạn có giá cuối tuần cố định; đối thủ cuối tuần thấp hơn nhưng tăng theo cầu.
        weekend = {4: 1.10, 5: 1.18} if h.dynamic else {4: 1.08, 5: 1.27}
        p = h.base_price * weekend.get(d.weekday(), 1.0)
        if d in self.event:
            p *= 1.12
        if h.dynamic:
            p *= 1 + 0.55 * max(0.0, self.fill(h, d, at) - 0.5)
            p *= 1 + (_noise("price", h.key, d) - 0.5) * 0.06
        return _round_price(p)

    def offers(self, h: DemoHotel, d: date, at: datetime) -> tuple[RoomOffer, ...]:
        left = self.rooms_left(h, d, at)
        price = self.price(h, d, at)
        promo = h.promo is not None and d.weekday() < 4 and _noise("promo", h.key, d) < 0.5
        out: list[RoomOffer] = []
        remaining = left
        for i, (rid, name, share, factor) in enumerate(ROOM_TYPES):
            n = remaining if i == len(ROOM_TYPES) - 1 else min(remaining, round(left * share))
            remaining -= n
            if n <= 0:
                continue
            nr = Decimal(_round_price(price * factor))
            original = Decimal(_round_price(float(nr) / 0.85)) if promo else None
            rates = (
                RatePlan(
                    "Non-refundable",
                    nr,
                    "VND",
                    False,
                    False,
                    2,
                    original,
                    True,
                    h.promo if promo else None,
                ),
                RatePlan(
                    "Free cancellation · Breakfast included",
                    Decimal(_round_price(float(nr) * 1.12)),
                    "VND",
                    True,
                    True,
                    2,
                    None,
                    True,
                ),
            )
            # Booking: "Only N left" khi ≤ 5; dropdown chọn số phòng chặn ở 10.
            badge = n if n <= 5 else None
            out.append(RoomOffer(f"{h.key}-{rid}", name, 2, badge, min(n, 10), rates))
        return tuple(out)


class ScenarioCollector:
    """Collector thay Booking.com: trả lịch và trang theo `Scenario` tại giờ của đồng hồ quét."""

    def __init__(self, scenario: Scenario, clock: FixedClock, by_id: dict[int, DemoHotel]) -> None:
        self._sc = scenario
        self._clock = clock
        self._by_id = by_id

    async def fetch_calendar(
        self, hotel: ListingRef, start: date, days: int, adults: int, rooms: int = 1
    ) -> CalendarResult:
        h, at = self._by_id[hotel.hotel_id], self._clock.now()
        out = []
        for i in range(days):
            d = start + timedelta(days=i)
            # Đêm đầu cửa sổ luôn "mở" (lịch 1 phòng của Booking hay trễ trong ngày) để worker probe
            # trực tiếp; các nấc N phòng của thang thì theo đúng phòng còn.
            left = self._sc.rooms_left(h, d, at)
            available = left >= rooms or (i == 0 and rooms == 1)
            out.append(CalendarDay(d, available, 1, None))
        return CalendarResult(ok=True, days=tuple(out))

    async def probe(
        self, hotel: ListingRef, checkin: date, nights: int, adults: int
    ) -> ProbeResult:
        h, at = self._by_id[hotel.hotel_id], self._clock.now()
        stay = [checkin + timedelta(days=i) for i in range(nights)]
        sold_out = any(self._sc.rooms_left(h, d, at) == 0 for d in stay)
        return ProbeResult(
            status=ProbeStatus.SOLD_OUT if sold_out else ProbeStatus.OK,
            method=ProbeMethod.HTTP,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=adults,
            offers=() if sold_out else self._sc.offers(h, checkin, at),
            raw_html=None,
            http_status=200,
            session_id="demo",
            duration_ms=800,
            external_id=hotel.external_id,
            hotel_name=h.name,
        )

    async def close(self) -> None:
        return None


def _scan_slots(now: datetime) -> list[datetime]:
    """Các mốc quét 06/14/22 giờ trong HISTORY_DAYS ngày qua, tới mốc gần nhất ≤ now."""
    today = now.astimezone(TZ).date()
    slots = [
        datetime.combine(today - timedelta(days=back), t, TZ)
        for back in range(HISTORY_DAYS, -1, -1)
        for t in SCAN_TIMES
    ]
    return [s.astimezone(UTC) for s in slots if s <= now]


async def _create_tenant(
    s, scenario: Scenario, now: datetime
) -> tuple[Tenant, dict[int, DemoHotel]]:
    tenant = Tenant(
        name=TENANT_NAME,
        timezone="Asia/Ho_Chi_Minh",
        scan_times=[t.strftime("%H:%M") for t in SCAN_TIMES],
        horizon_days=HORIZON_DAYS,
        country_code="vn",
        active=True,
        setup_state={"dismissed_at": now.isoformat()},  # ẩn thẻ "Thiết lập 5 bước" khi quay
    )
    s.add(tenant)
    await s.flush()
    by_id: dict[int, DemoHotel] = {}
    for i, h in enumerate(HOTELS):
        slug = f"vn/otaradar-demo-{h.key}"
        hotel = Hotel(
            name=h.name,
            city="Đà Nẵng",
            country_code="vn",
            star_rating=Decimal(4),
            address="Đà Nẵng (địa chỉ minh hoạ)",
            lat=h.lat,
            lng=h.lng,
            review_score=Decimal(h.review),
            review_count=600 + i * 137,
            district="Hải Châu",
            rooms_total=h.rooms_total,
            rooms_total_source="Website khách sạn (minh hoạ)",
            rooms_total_updated_at=now,
        )
        s.add(hotel)
        await s.flush()
        by_id[hotel.id] = h
        s.add_all(
            [
                Listing(
                    hotel_id=hotel.id,
                    channel="booking",
                    listing_key=slug,
                    external_id=str(990001 + i),
                    url=f"https://www.booking.com/hotel/{slug}.html",
                    name=h.name,
                    status="active",
                    verified_at=now,
                ),
                TenantHotel(
                    tenant_id=tenant.id, hotel_id=hotel.id, role=h.role, label=h.label, active=True
                ),
            ]
        )
    s.add(
        User(
            tenant_id=tenant.id,
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            role="tenant_admin",
            active=True,
        )
    )
    s.add(
        LocalEvent(
            tenant_id=tenant.id,
            name="Hội nghị Y khoa quốc tế",
            category="mice",
            start_date=scenario.event[0],
            end_date=scenario.event[1],
            expected_uplift_pct=20,
            note="Sự kiện minh hoạ cho video",
        )
    )
    await s.flush()
    return tenant, by_id


async def _simulate_scans(factory, settings, scenario: Scenario, by_id, slots) -> list[int]:
    """Mỗi mốc quét: tạo run + job như scheduler, chạy job worker với collector kịch bản, rồi
    analytics như worker `jobs`."""
    clock = FixedClock(slots[0])
    deps = WorkerDeps(
        session_factory=factory,
        collector=ScenarioCollector(scenario, clock, by_id),
        raw_store=MemoryRawStore(),
        clock=clock,
        page_cap=settings.page_dropdown_cap,
        default_adults=2,
        parser_version="demo",
        alerter=NullAlerter(),
        worker_id="video-demo",
        capacity_rungs=settings.capacity_rungs,
    )
    run_ids = []
    for at in slots:
        clock.advance(seconds=(at - clock.now()).total_seconds())
        local_day = at.astimezone(TZ).date()
        async with factory() as s:
            run = await ScanRunRepository(s).create_run(
                f"video-demo:{at.isoformat()}",
                at,
                [HotelJobPlan(hid, local_day, HORIZON_DAYS) for hid in by_id],
            )
            await s.commit()
        for hid in by_id:
            await run_probe_hotel(deps, run.id, hid, final_attempt=True)
        async with factory() as s:
            await AnalyticsService(
                s, settings.low_stock_threshold, settings.price_change_threshold_pct
            ).run(run.id)
            await s.commit()
        run_ids.append(run.id)
        print(f"  run {run.id} {at.astimezone(TZ):%d/%m %H:%M}", flush=True)
    async with factory() as s:
        svc = OccupancyService(s)
        while pending := await svc.pending_run_ids():
            for rid in pending:
                await svc.run(rid)
                await s.commit()
    return run_ids


async def _seed_pms(s, tenant_id: int, hotel_id: int, scenario: Scenario, now: datetime) -> None:
    """OTB từ PMS 30 đêm tới (như file ezCloud đã nhập). 14 đêm gần ở 72–79% (đủ cao để app không
    gợi ý giảm giá sát ngày), thứ Bảy của video và hội nghị trên 80%, xa hơn thấp dần."""
    own = next(h for h in HOTELS if h.role == "self")
    for i in range(30):
        d = scenario.today + timedelta(days=i)
        if d == scenario.hero:
            occ = 0.86
        elif d in scenario.event:
            occ = 0.82
        elif i < 14:
            occ = 0.72 + 0.07 * _noise("otb", d)
        else:
            occ = 0.58 + 0.12 * _noise("otb", d)
        sold = int(own.rooms_total * occ)
        s.add(
            OwnHotelDaily(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                stay_date=d,
                rooms_total=own.rooms_total,
                rooms_sold=sold,
                rooms_available=own.rooms_total - sold,
                occupancy_pct=Decimal(sold * 100 / own.rooms_total).quantize(Decimal("0.01")),
                adr=Decimal(scenario.price(own, d, now)),
                revenue=None,
                source="csv",
                imported_at=now,
            )
        )


AREA_PREFIX = (
    "Hải Âu",
    "Phương Đông",
    "Bạch Đằng",
    "Mỹ An",
    "Sơn Trà",
    "Hoàng Sa",
    "Thanh Bình",
    "Phú An",
    "Lotus",
    "Azure",
    "Riverside",
    "Golden Sand",
    "Sunrise",
    "Coral",
)
AREA_SUFFIX = (
    "Hotel",
    "Boutique Hotel",
    "Hotel & Spa",
    "Central Hotel",
    "Ocean Hotel",
    "Residence",
    "Plaza Hotel",
)


def _area_hotels() -> list[tuple[str, str, int, float, float, float]]:
    """~45 khách sạn giả quanh khách sạn của bạn: (slug, tên, hạng sao, độ hút khách, lat, lng)."""
    out = []
    for i in range(45):
        name = f"{AREA_PREFIX[i % len(AREA_PREFIX)]} {AREA_SUFFIX[(i * 3) % len(AREA_SUFFIX)]}"
        r = random.Random(f"area-{i}")
        out.append(
            (
                f"vn/otaradar-demo-area-{i:02d}",
                name,
                r.choice((3, 3, 4, 4, 4, 5)),
                r.uniform(0.7, 1.25),
                CENTER[0] + r.uniform(-0.02, 0.02),
                CENTER[1] + r.uniform(-0.02, 0.02),
            )
        )
    return out


async def _seed_market(s, tenant_id: int, scenario: Scenario, rungs, at: datetime) -> None:
    """Khu vực bán kính 3 km quanh khách sạn của bạn, lượt quét 14 đêm gần nhất (dạng
    `MarketListService` ghi: danh sách 1 phòng + thang N phòng)."""
    own = next(h for h in HOTELS if h.role == "self")
    area = MarketArea(
        tenant_id=tenant_id,
        channel="booking",
        name="Bán kính 3 km quanh Sao Mai Riverside",
        dest_id=f"{own.lat},{own.lng}",
        dest_type="latlong",
        country_code="vn",
        lat=own.lat,
        lng=own.lng,
        radius_m=3000,
        list_nights=14,
        detail_max_hotels=0,
        last_list_scan_at=at,
        last_list_status="completed",
    )
    s.add(area)
    await s.flush()
    others = _area_hotels()
    total = len(others) + len(HOTELS)
    for night in range(14):
        d = scenario.today + timedelta(days=night)
        # (thẻ, phòng còn) của mọi khách sạn còn bán đêm này
        avail: list[tuple[SearchCard, int]] = []
        for h in HOTELS:
            left = scenario.rooms_left(h, d, at)
            if left:
                avail.append(
                    (
                        _card(
                            f"vn/otaradar-demo-{h.key}",
                            h.name,
                            4,
                            h.lat,
                            h.lng,
                            scenario.price(h, d, at),
                            h.review,
                        ),
                        left,
                    )
                )
        for slug, name, stars, pop, lat, lng in others:
            demand = scenario.demand(d) * pop * (1 / (1 + (night / 10) ** 1.3))
            left = int(30 * (1 - min(demand, 1.0)) * _noise("left", slug, d))
            if left:
                price = _round_price((500_000 + stars * 250_000) * (0.85 + demand * 0.45))
                avail.append((_card(slug, name, stars, lat, lng, price, f"{7.6 + pop:.1f}"), left))
        ladder = {
            str(n): {
                "available": sum(1 for _, left in avail if left >= n),
                "autoextended": 0,
                "class": {},
            }
            for n in rungs
        }
        found = len(avail)
        scan = MarketListScan(
            area_id=area.id,
            stay_date=d,
            scanned_at=at,
            finished_at=at + timedelta(minutes=4),
            properties_found=found,
            pages=1 + len(rungs),
            hotels_seen=found,
            priced=found,
            status="completed",
            source="graphql",
            nflt=area_scope(area),
            autoextended=0,
            low_availability=found < total * 0.3,
            unavailability_pct=round(100 * (1 - found / total)),
            market_available=found,
            market_facets={"ht_id=204": found},
            facets={"ht_id=204": found},
            ladder=ladder,
            enumerated=True,
        )
        s.add(scan)
        await s.flush()
        ranked = sorted(avail, key=lambda x: -_noise("rank", x[0].slug))
        await record_page(
            s,
            area_id=area.id,
            scan_id=scan.id,
            channel="booking",
            ranked=[(i + 1, card) for i, (card, _) in enumerate(ranked)],
            now=at,
            round_started=at,
            currency="VND",
        )
        for n in rungs:
            await record_rung(
                s,
                area_id=area.id,
                scan_id=scan.id,
                channel="booking",
                cards=[c for c, left in avail if left >= n],
                rooms=n,
                now=at,
                round_started=at,
            )


def _card(slug, name, stars, lat, lng, price, review) -> SearchCard:
    return SearchCard(
        slug=slug,
        url=f"https://www.booking.com/hotel/{slug}.html",
        name=name,
        external_id=str(int(hashlib.sha256(slug.encode()).hexdigest()[:6], 16)),
        review_score=Decimal(review),
        review_count=200 + int(_noise("reviews", slug) * 1500),
        stars=Decimal(stars),
        city="Đà Nẵng",
        district="Hải Châu",
        lat=lat,
        lng=lng,
        price=Decimal(price),
        currency="VND",
        type_id=204,
    )


async def main() -> None:
    settings = get_settings()
    db = make_url(settings.database_url).database or ""
    if not db.endswith("_demo"):
        raise SystemExit(f"Từ chối: database '{db}' không phải database demo (*_demo).")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    now = datetime.now(tz=UTC)
    slots = _scan_slots(now)
    scenario = Scenario(now.astimezone(TZ).date(), slots[-1])
    async with factory() as s:
        if (await s.execute(Tenant.__table__.select().limit(1))).first():
            raise SystemExit("Database demo đã có dữ liệu: chạy `make demo-video-db` để tạo lại.")
        await ensure_room_snapshot_partitions(
            await s.connection(), scenario.today - timedelta(days=HISTORY_DAYS + 1), 5
        )
        tenant, by_id = await _create_tenant(s, scenario, now)
        await s.commit()
    print(f"tenant {tenant.id}: mô phỏng {len(slots)} lượt quét…", flush=True)
    await _simulate_scans(factory, settings, scenario, by_id, slots)
    own_id = next(hid for hid, h in by_id.items() if h.role == "self")
    async with factory() as s:
        await _seed_pms(s, tenant.id, own_id, scenario, slots[-1])
        await _seed_market(s, tenant.id, scenario, settings.capacity_rungs, slots[-1])
        await s.commit()
    await engine.dispose()
    last = slots[-1].astimezone(TZ)
    print(f"xong. Thứ Bảy của video: {scenario.hero:%d/%m}; hội nghị {scenario.event[0]:%d/%m}.")
    print(
        f"lượt quét cuối {last:%d/%m %H:%M}; gợi ý giá tạm dừng sau {last + timedelta(hours=10):%d/%m %H:%M}."
    )
    print(f"đăng nhập: {EMAIL} (mật khẩu trong docstring của script)")


if __name__ == "__main__":
    asyncio.run(main())
