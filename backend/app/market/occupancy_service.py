"""Ghi công suất ước tính cho mỗi (khách sạn, kênh, đêm) của một lượt quét đã analytics.

Chạy bằng cron bù (`estimate_occupancy_catch_up`), không móc vào analytics: lượt quét nào đã có
`hotel_date_snapshots` mà chưa có dấu `occupancy_estimate_runs` thì được xử lý (cũ trước, giới hạn
mỗi lần), nên lịch sử cũ cũng được tính dần. Idempotent theo (khách sạn, kênh, đêm, lượt quét).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import case, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HotelDateSnapshot, Probe, RoomSnapshot, ScanRun
from app.logging import get_logger
from app.market.models import OccupancyEstimate, OccupancyEstimateRun
from app.market.occupancy import RoomState, estimate

log = get_logger(__name__)

INVENTORY_WINDOW = timedelta(days=30)  # cùng cửa sổ "loại phòng còn hoạt động" của analytics
# Chỉ số phòng theo loại phòng; số theo gói giá (stock_scope="rate", vài kênh) không cộng được.
ROOM_SCOPE = "room_type"
FAILED = -1  # dấu lượt ước tính lỗi: không lấy lại tự động (xoá dấu để tính lại)
BATCH_RUNS = 20


class OccupancyService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def pending_run_ids(self, limit: int = BATCH_RUNS) -> list[int]:
        rows = await self._s.execute(
            select(ScanRun.id)
            .where(
                ScanRun.status.in_(["completed", "partial"]),
                exists().where(HotelDateSnapshot.scan_run_id == ScanRun.id),
                ~exists().where(OccupancyEstimateRun.scan_run_id == ScanRun.id),
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

    async def mark_failed(self, run_id: int) -> None:
        """Ghi dấu lỗi để lượt hỏng không chặn đầu hàng đợi mãi (head-of-line)."""
        await self._s.execute(
            insert(OccupancyEstimateRun)
            .values(scan_run_id=run_id, rows=FAILED)
            .on_conflict_do_nothing(index_elements=[OccupancyEstimateRun.scan_run_id])
        )

    async def run(self, run_id: int) -> int:
        snaps = list(
            (
                await self._s.execute(
                    select(HotelDateSnapshot).where(
                        HotelDateSnapshot.scan_run_id == run_id,
                        HotelDateSnapshot.status.in_(["available", "sold_out"]),
                    )
                )
            ).scalars()
        )
        rooms = await self._run_rooms(run_id) if snaps else {}
        inventories: dict[tuple[int, str], dict[int, int]] = {}
        written = 0
        for snap in snaps:
            key = (snap.hotel_id, snap.channel)
            if key not in inventories:
                last = max(s.scanned_at for s in snaps if (s.hotel_id, s.channel) == key)
                inventories[key] = await self._inventory(snap.hotel_id, snap.channel, last)
            est = estimate(
                snap.status, rooms.get((snap.hotel_id, snap.stay_date), []), inventories[key]
            )
            if est is None:
                continue
            values = dict(
                hotel_id=snap.hotel_id,
                channel=snap.channel,
                stay_date=snap.stay_date,
                scan_run_id=run_id,
                scanned_at=snap.scanned_at,
                days_to_arrival=(snap.stay_date - snap.scanned_at.date()).days,
                status=snap.status,
                inventory=est.inventory,
                left_low=est.left_low,
                left_high=est.left_high,
                occ_low=est.occ_low,
                occ_high=est.occ_high,
                coverage=est.coverage,
            )
            await self._s.execute(
                insert(OccupancyEstimate)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        OccupancyEstimate.hotel_id,
                        OccupancyEstimate.channel,
                        OccupancyEstimate.stay_date,
                        OccupancyEstimate.scan_run_id,
                    ],
                    set_={
                        k: v
                        for k, v in values.items()
                        if k not in ("hotel_id", "channel", "stay_date", "scan_run_id")
                    },
                )
            )
            written += 1
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
