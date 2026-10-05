"""Ghi công suất ước tính cho mỗi (khách sạn, kênh, đêm) của một lượt quét đã analytics.

Chạy bằng cron bù (`estimate_occupancy_catch_up`), không móc vào analytics: lượt quét nào đã có
`hotel_date_snapshots` mà chưa có dấu `occupancy_estimate_runs` thì được xử lý (cũ trước, giới hạn
mỗi lần), nên lịch sử cũ cũng được tính dần. Idempotent theo (khách sạn, kênh, đêm, lượt quét).

Lượt lỗi: dấu ghi `rows` âm = số lần thử (−1, −2, −3); thử lại sau RETRY_AFTER, tối đa MAX_ATTEMPTS
lần (≈ 3 lần/ngày) rồi để nguyên. `reset_occupancy_marker` xoá dấu để tính lại (sau reparse).
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import country_timezone, local_date
from app.db.models import Hotel, HotelDateSnapshot, Probe, RoomSnapshot, ScanRun
from app.logging import get_logger
from app.market.models import OccupancyEstimate, OccupancyEstimateRun
from app.market.occupancy import RoomState, estimate

log = get_logger(__name__)

INVENTORY_WINDOW = timedelta(days=30)  # cùng cửa sổ "loại phòng còn hoạt động" của analytics
# Chỉ số phòng theo loại phòng; số theo gói giá (stock_scope="rate", vài kênh) không cộng được.
ROOM_SCOPE = "room_type"
BATCH_RUNS = 20
INSERT_CHUNK = 500
MAX_ATTEMPTS = 3  # lượt lỗi quá số lần này thì thôi (xoá dấu để tính lại)
RETRY_AFTER = timedelta(hours=8)  # cách nhau tối thiểu giữa hai lần thử → ≤ 3 lần/ngày

_ESTIMATE_COLUMNS = (
    "scanned_at",
    "days_to_arrival",
    "status",
    "inventory",
    "left_low",
    "left_high",
    "occ_low",
    "occ_high",
    "coverage",
)


async def reset_occupancy_marker(session: AsyncSession, scan_run_id: int) -> bool:
    """Xoá dấu đã ước tính của một lượt quét để cron tính lại (sau reparse/analyze lại)."""
    result = await session.execute(
        delete(OccupancyEstimateRun).where(OccupancyEstimateRun.scan_run_id == scan_run_id)
    )
    return bool(getattr(result, "rowcount", 0))


class OccupancyService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def pending_run_ids(
        self, limit: int = BATCH_RUNS, now: datetime | None = None
    ) -> list[int]:
        """Lượt chưa có dấu, hoặc dấu lỗi còn trong hạn thử lại (chưa đủ MAX_ATTEMPTS, đã qua
        RETRY_AFTER kể từ lần thử trước)."""
        cutoff = (now or datetime.now(tz=UTC)) - RETRY_AFTER
        rows = await self._s.execute(
            select(ScanRun.id)
            .outerjoin(OccupancyEstimateRun, OccupancyEstimateRun.scan_run_id == ScanRun.id)
            .where(
                ScanRun.status.in_(["completed", "partial"]),
                exists().where(HotelDateSnapshot.scan_run_id == ScanRun.id),
                or_(
                    OccupancyEstimateRun.scan_run_id.is_(None),
                    and_(
                        OccupancyEstimateRun.rows < 0,
                        OccupancyEstimateRun.rows > -MAX_ATTEMPTS,
                        OccupancyEstimateRun.estimated_at <= cutoff,
                    ),
                ),
            )
            .order_by(ScanRun.finished_at)
            .limit(limit)
        )
        return [r[0] for r in rows]

    async def _inventory(self, hotel_id: int, channel: str, until: datetime) -> dict[int, int]:
        """Tồn phòng nhìn thấy mỗi loại phòng trong cửa sổ kết thúc ở lần quét này."""
        # Cùng quy tắc với RoomState.floor: chính xác = rooms_left; "ít nhất" = mức sàn.
        floor = case(
            (RoomSnapshot.stock_confidence == "exact", RoomSnapshot.rooms_left),
            else_=func.coalesce(RoomSnapshot.rooms_left, RoomSnapshot.dropdown_max),
        )
        rows = await self._s.execute(
            select(RoomSnapshot.room_type_id, func.max(floor))
            .where(
                RoomSnapshot.hotel_id == hotel_id,
                RoomSnapshot.channel == channel,
                RoomSnapshot.scanned_at >= until - INVENTORY_WINDOW,
                RoomSnapshot.scanned_at <= until,
                RoomSnapshot.stock_confidence.in_(["exact", "capped"]),
                RoomSnapshot.stock_scope == ROOM_SCOPE,
            )
            .group_by(RoomSnapshot.room_type_id)
        )
        return {rt: int(v) for rt, v in rows if v is not None and v > 0}

    async def _run_rooms(self, run_id: int) -> dict[tuple[int, date], list[RoomState]]:
        bounds = (
            await self._s.execute(
                select(func.min(Probe.fetched_at), func.max(Probe.fetched_at)).where(
                    Probe.scan_run_id == run_id
                )
            )
        ).one()
        if bounds[0] is None:
            return {}
        rows = await self._s.execute(
            select(
                RoomSnapshot.hotel_id,
                RoomSnapshot.stay_date,
                RoomSnapshot.room_type_id,
                RoomSnapshot.stock_confidence,
                RoomSnapshot.rooms_left,
                RoomSnapshot.dropdown_max,
            )
            .join(Probe, Probe.id == RoomSnapshot.probe_id)
            .where(
                Probe.scan_run_id == run_id,
                RoomSnapshot.stock_scope == ROOM_SCOPE,
                # room_snapshots chia partition theo scanned_at: chặn khoảng để không quét mọi tháng
                RoomSnapshot.scanned_at >= bounds[0],
                RoomSnapshot.scanned_at <= bounds[1],
            )
        )
        out: dict[tuple[int, date], list[RoomState]] = defaultdict(list)
        for hotel_id, stay, rt, conf, left, dmax in rows:
            out[(hotel_id, stay)].append(RoomState(rt, conf, left, dmax))
        return out

    async def mark_failed(self, run_id: int) -> int:
        """Ghi dấu lỗi để lượt hỏng không chặn đầu hàng đợi (head-of-line); `rows` âm đếm số lần
        thử để cron thử lại có giới hạn. Trả về số lần đã thử."""
        attempts = (
            await self._s.execute(
                insert(OccupancyEstimateRun)
                .values(scan_run_id=run_id, rows=-1)
                .on_conflict_do_update(
                    index_elements=[OccupancyEstimateRun.scan_run_id],
                    set_={
                        "rows": case(
                            (OccupancyEstimateRun.rows < 0, OccupancyEstimateRun.rows - 1),
                            else_=-1,
                        ),
                        "estimated_at": func.now(),
                    },
                )
                .returning(OccupancyEstimateRun.rows)
            )
        ).scalar_one()
        return -attempts

    async def run(self, run_id: int) -> int:
        snaps = (
            await self._s.execute(
                select(HotelDateSnapshot, Hotel.country_code)
                .join(Hotel, Hotel.id == HotelDateSnapshot.hotel_id)
                .where(
                    HotelDateSnapshot.scan_run_id == run_id,
                    HotelDateSnapshot.status.in_(["available", "sold_out"]),
                )
            )
        ).all()
        rooms = await self._run_rooms(run_id) if snaps else {}
        # Mốc kết thúc cửa sổ tồn phòng = lần quét muộn nhất của (khách sạn, kênh) trong lượt này.
        last_scanned: dict[tuple[int, str], datetime] = {}
        for snap, _ in snaps:
            key = (snap.hotel_id, snap.channel)
            if key not in last_scanned or snap.scanned_at > last_scanned[key]:
                last_scanned[key] = snap.scanned_at
        inventories = {
            key: await self._inventory(key[0], key[1], until) for key, until in last_scanned.items()
        }
        values: list[dict[str, object]] = []
        for snap, country_code in snaps:
            est = estimate(
                snap.status,
                rooms.get((snap.hotel_id, snap.stay_date), []),
                inventories[(snap.hotel_id, snap.channel)],
            )
            if est is None:
                continue
            # Số ngày tới khi đến theo ngày địa phương của khách sạn: quét 06:00 Việt Nam là 23:00
            # UTC hôm trước, lấy ngày UTC sẽ lệch một ngày so với mốc 14:00/22:00 cùng ngày.
            scan_day = local_date(snap.scanned_at, country_timezone(country_code))
            values.append(
                dict(
                    hotel_id=snap.hotel_id,
                    channel=snap.channel,
                    stay_date=snap.stay_date,
                    scan_run_id=run_id,
                    scanned_at=snap.scanned_at,
                    days_to_arrival=(snap.stay_date - scan_day).days,
                    status=snap.status,
                    inventory=est.inventory,
                    left_low=est.left_low,
                    left_high=est.left_high,
                    occ_low=est.occ_low,
                    occ_high=est.occ_high,
                    coverage=est.coverage,
                )
            )
        for i in range(0, len(values), INSERT_CHUNK):
            stmt = insert(OccupancyEstimate).values(values[i : i + INSERT_CHUNK])
            await self._s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[
                        OccupancyEstimate.hotel_id,
                        OccupancyEstimate.channel,
                        OccupancyEstimate.stay_date,
                        OccupancyEstimate.scan_run_id,
                    ],
                    set_={c: getattr(stmt.excluded, c) for c in _ESTIMATE_COLUMNS},
                )
            )
        written = len(values)
        await self._s.execute(
            insert(OccupancyEstimateRun)
            .values(scan_run_id=run_id, rows=written)
            .on_conflict_do_update(
                index_elements=[OccupancyEstimateRun.scan_run_id],
                set_={"rows": written, "estimated_at": func.now()},
            )
        )
        log.info("occupancy_estimated", run_id=run_id, rows=written)
        return written
