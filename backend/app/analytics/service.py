"""AnalyticsService: chạy khi một scan run chốt, idempotent theo scan_run_id.

1. Gộp room_snapshots của run thành hotel_date_snapshots.
2. So với lần quan sát dùng được gần nhất, sinh availability_events.
3. Cập nhật hotel_date_metrics.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.cross_channel import (
    FRESH_FOR,
    ChannelView,
    channel_closed,
    parity_gap,
    rates_tax_inclusive,
)
from app.analytics.rules import (
    DateStatus,
    EventDraft,
    EventType,
    HotelDateObs,
    KnownValues,
    RoomObs,
    Thresholds,
    compute_metrics,
    date_status_for_probe,
    diff_events,
    last_usable_before,
)
from app.clock import country_timezone, local_date
from app.db.models import (
    AvailabilityEvent,
    Hotel,
    HotelDateMetric,
    HotelDateSnapshot,
    Probe,
    RoomSnapshot,
    RoomType,
    ScanRun,
    TenantHotel,
)
from app.domain.models import StockConfidence
from app.logging import get_logger
from app.ops.metrics import ANALYTICS_RUNS, EVENTS_TOTAL

log = get_logger(__name__)

HISTORY_WINDOW = timedelta(days=8)
ROOM_TYPE_ACTIVE_WINDOW = timedelta(days=30)


@dataclass
class AnalyticsReport:
    scan_run_id: int
    hotel_dates: int = 0
    events: int = 0
    metrics: int = 0


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        low_stock_threshold: int = 3,
        price_change_threshold_pct: float = 3.0,
    ) -> None:
        self._s = session
        self._thresholds = Thresholds(
            low_stock=low_stock_threshold,
            price_change_pct=Decimal(str(price_change_threshold_pct)),
        )

    async def pending_run_ids(self) -> list[int]:
        """Run đã chốt nhưng chưa có hotel_date_snapshots (chưa chạy analytics)."""
        analyzed = select(HotelDateSnapshot.scan_run_id).distinct()
        rows = await self._s.execute(
            select(ScanRun.id)
            .where(
                ScanRun.status.in_(["completed", "partial"]),
                ScanRun.total_probes > 0,
                ScanRun.id.not_in(analyzed),
            )
            .order_by(ScanRun.finished_at)
        )
        return [r[0] for r in rows]

    async def run(self, scan_run_id: int) -> AnalyticsReport:
        report = AnalyticsReport(scan_run_id)
        try:
            channel = (
                await self._s.execute(select(ScanRun.channel).where(ScanRun.id == scan_run_id))
            ).scalar_one()
            # Nước của khách sạn → múi giờ cho days_to_arrival (06:00 VN là 23:00 UTC hôm trước).
            hotels = (
                await self._s.execute(
                    select(Probe.hotel_id, Hotel.country_code)
                    .join(Hotel, Hotel.id == Probe.hotel_id)
                    .where(Probe.scan_run_id == scan_run_id)
                    .distinct()
                    .order_by(Probe.hotel_id)
                )
            ).all()
            # Idempotent: xoá sự kiện của run này rồi tính lại.
            await self._s.execute(
                delete(AvailabilityEvent).where(AvailabilityEvent.scan_run_id == scan_run_id)
            )
            for hotel_id, country in hotels:
                await self._process_hotel(
                    scan_run_id, hotel_id, channel, country_timezone(country), report
                )
            await self._s.flush()
            for hotel_id, _ in hotels:
                await self._cross_channel(scan_run_id, hotel_id, channel, report)
            await self._s.flush()
            ANALYTICS_RUNS.labels("ok").inc()
            log.info(
                "analytics_done",
                run_id=scan_run_id,
                hotel_dates=report.hotel_dates,
                events=report.events,
            )
        except Exception:
            ANALYTICS_RUNS.labels("error").inc()
            raise
        return report

    async def _load_current(self, scan_run_id: int, hotel_id: int) -> dict[date, HotelDateObs]:
        probes = (
            (
                await self._s.execute(
                    select(Probe).where(
                        Probe.scan_run_id == scan_run_id, Probe.hotel_id == hotel_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not probes:
            return {}
        snaps = (
            (
                await self._s.execute(
                    select(RoomSnapshot).where(RoomSnapshot.probe_id.in_([p.id for p in probes]))
                )
            )
            .scalars()
            .all()
        )
        by_probe: dict[int, list[RoomSnapshot]] = defaultdict(list)
        for s in snaps:
            by_probe[s.probe_id].append(s)
        out: dict[date, HotelDateObs] = {}
        for p in probes:
            rooms = {
                s.room_type_id: RoomObs(
                    s.room_type_id,
                    s.rooms_left,
                    StockConfidence(s.stock_confidence),
                    s.min_price,
                    s.min_refundable_price,
                )
                for s in by_probe.get(p.id, [])
            }
            status = date_status_for_probe(p.status)
            if status == DateStatus.AVAILABLE and not rooms:
                # ok nhưng không parse ra phòng nào: không dùng được
                status = DateStatus.UNKNOWN
            currency = next((s.currency for s in by_probe.get(p.id, []) if s.currency), None)
            out[p.stay_date] = HotelDateObs(
                scan_run_id=scan_run_id,
                scanned_at=p.fetched_at,
                status=status,
                rooms=rooms,
                currency=currency,
            )
        return out

    async def _load_history(
        self, scan_run_id: int, hotel_id: int, channel: str, dates: list[date], since: datetime
    ) -> dict[date, list[HotelDateObs]]:
        rows = (
            (
                await self._s.execute(
                    select(HotelDateSnapshot).where(
                        HotelDateSnapshot.hotel_id == hotel_id,
                        HotelDateSnapshot.channel == channel,
                        HotelDateSnapshot.stay_date.in_(dates),
                        HotelDateSnapshot.scan_run_id != scan_run_id,
                        HotelDateSnapshot.scanned_at >= since,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return {}
        # room snapshots của các lần quan sát trước, khoá theo (stay_date, scanned_at)
        snaps = (
            (
                await self._s.execute(
                    select(RoomSnapshot).where(
                        RoomSnapshot.hotel_id == hotel_id,
                        RoomSnapshot.channel == channel,
                        RoomSnapshot.stay_date.in_(dates),
                        RoomSnapshot.scanned_at >= since,
                    )
                )
            )
            .scalars()
            .all()
        )
        rooms_by_key: dict[tuple[date, datetime], dict[int, RoomObs]] = defaultdict(dict)
        for s in snaps:
            rooms_by_key[(s.stay_date, s.scanned_at)][s.room_type_id] = RoomObs(
                s.room_type_id,
                s.rooms_left,
                StockConfidence(s.stock_confidence),
                s.min_price,
                s.min_refundable_price,
            )
        history: dict[date, list[HotelDateObs]] = defaultdict(list)
        for r in rows:
            history[r.stay_date].append(
                HotelDateObs(
                    scan_run_id=r.scan_run_id,
                    scanned_at=r.scanned_at,
                    status=DateStatus(r.status),
                    rooms=rooms_by_key.get((r.stay_date, r.scanned_at), {}),
                    currency=r.currency,
                )
            )
        return history

    async def _known_room_type_count(self, hotel_id: int, channel: str, as_of: datetime) -> int:
        n = await self._s.execute(
            select(func.count())
            .select_from(RoomType)
            .where(
                RoomType.hotel_id == hotel_id,
                RoomType.channel == channel,
                RoomType.last_seen_at >= as_of - ROOM_TYPE_ACTIVE_WINDOW,
            )
        )
        return int(n.scalar_one())

    async def _process_hotel(
        self, scan_run_id: int, hotel_id: int, channel: str, tz: str, report: AnalyticsReport
    ) -> None:
        current = await self._load_current(scan_run_id, hotel_id)
        if not current:
            return
        dates = sorted(current)
        earliest = min(o.scanned_at for o in current.values())
        history = await self._load_history(
            scan_run_id, hotel_id, channel, dates, earliest - HISTORY_WINDOW
        )
        known_types = await self._known_room_type_count(hotel_id, channel, earliest)

        for stay_date in dates:
            cur = current[stay_date]
            hist = history.get(stay_date, [])
            # 1. hotel_date_snapshots
            await self._upsert_hotel_date(hotel_id, channel, stay_date, cur, known_types)
            report.hotel_dates += 1
            # 2. events
            prev = last_usable_before(hist, cur.scanned_at)
            drafts = diff_events(prev, cur, self._thresholds)
            for d in drafts:
                await self._insert_event(
                    scan_run_id, hotel_id, channel, stay_date, cur.scanned_at, d
                )
                EVENTS_TOTAL.labels(str(d.event_type)).inc()
            report.events += len(drafts)
            # 3. metrics (chỉ khi lần này mới hơn lần đã ghi)
            gone = frozenset(
                d.room_type_id
                for d in drafts
                if d.event_type == EventType.ROOM_TYPE_GONE and d.room_type_id is not None
            )
            if await self._upsert_metrics(
                scan_run_id, hotel_id, channel, stay_date, cur, hist, tz, gone
            ):
                report.metrics += 1

    async def _upsert_hotel_date(
        self, hotel_id: int, channel: str, stay_date: date, cur: HotelDateObs, known_types: int
    ) -> None:
        if cur.status == DateStatus.SOLD_OUT:
            sold_out_types = known_types
        elif cur.status == DateStatus.AVAILABLE:
            sold_out_types = max(0, known_types - cur.room_types_available)
        else:
            sold_out_types = 0
        values = dict(
            hotel_id=hotel_id,
            channel=channel,
            stay_date=stay_date,
            scan_run_id=cur.scan_run_id,
            scanned_at=cur.scanned_at,
            status=str(cur.status),
            exact_rooms_left=cur.exact_rooms_left if cur.usable else None,
            room_types_available=cur.room_types_available if cur.usable else 0,
            room_types_sold_out=sold_out_types,
            min_price=cur.min_price if cur.usable else None,
            min_refundable_price=cur.min_refundable_price if cur.usable else None,
            currency=cur.currency if cur.usable else None,
        )
        stmt = (
            insert(HotelDateSnapshot)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    HotelDateSnapshot.hotel_id,
                    HotelDateSnapshot.stay_date,
                    HotelDateSnapshot.scan_run_id,
                ],
                set_={
                    k: v
                    for k, v in values.items()
                    if k not in ("hotel_id", "stay_date", "scan_run_id")
                },
            )
        )
        await self._s.execute(stmt)

    async def _insert_event(
        self,
        scan_run_id: int,
        hotel_id: int,
        channel: str,
        stay_date: date,
        observed_at: datetime,
        d: EventDraft,
    ) -> None:
        stmt = (
            insert(AvailabilityEvent)
            .values(
                hotel_id=hotel_id,
                channel=channel,
                room_type_id=d.room_type_id,
                stay_date=stay_date,
                event_type=str(d.event_type),
                from_value=d.from_value,
                to_value=d.to_value,
                delta=d.delta,
                confidence=d.confidence,
                previous_scan_run_id=d.previous_scan_run_id,
                scan_run_id=scan_run_id,
                observed_at=observed_at,
            )
            .on_conflict_do_nothing(constraint="uq_availability_events_run_scope")
        )
        await self._s.execute(stmt)

    async def _upsert_metrics(
        self,
        scan_run_id: int,
        hotel_id: int,
        channel: str,
        stay_date: date,
        cur: HotelDateObs,
        hist: list[HotelDateObs],
        tz: str,
        gone_room_types: frozenset[int] = frozenset(),
    ) -> bool:
        """Ghi metric nếu lần quan sát này không cũ hơn bản đã có. Probe không dùng được giữ
        giá/số phòng của bản hiện có (`KnownValues`) và chỉ đổi trạng thái + `stale_since`.

        Chọn cột (không nạp entity) để không giữ bản cũ trong identity map sau khi upsert bằng Core.
        """
        existing = (
            await self._s.execute(
                select(
                    HotelDateMetric.last_observed_at,
                    HotelDateMetric.stale_since,
                    HotelDateMetric.min_price,
                    HotelDateMetric.min_refundable_price,
                    HotelDateMetric.currency,
                    HotelDateMetric.exact_rooms_left,
                ).where(
                    HotelDateMetric.hotel_id == hotel_id,
                    HotelDateMetric.channel == channel,
                    HotelDateMetric.stay_date == stay_date,
                )
            )
        ).one_or_none()
        known: KnownValues | None = None
        if existing is not None:
            if existing.last_observed_at > cur.scanned_at:
                return False
            known = KnownValues(
                min_price=existing.min_price,
                min_refundable_price=existing.min_refundable_price,
                currency=existing.currency,
                exact_rooms_left=existing.exact_rooms_left,
                last_observed_at=existing.last_observed_at,
                stale_since=existing.stale_since,
            )
        days = (stay_date - local_date(cur.scanned_at, tz)).days
        m = compute_metrics(cur, hist, days, known, gone_room_types)
        sold_out_at = (
            await self._s.execute(
                select(func.max(AvailabilityEvent.observed_at)).where(
                    AvailabilityEvent.hotel_id == hotel_id,
                    AvailabilityEvent.channel == channel,
                    AvailabilityEvent.stay_date == stay_date,
                    AvailabilityEvent.event_type == "sold_out",
                )
            )
        ).scalar_one()
        restocked_at = (
            await self._s.execute(
                select(func.max(AvailabilityEvent.observed_at)).where(
                    AvailabilityEvent.hotel_id == hotel_id,
                    AvailabilityEvent.channel == channel,
                    AvailabilityEvent.stay_date == stay_date,
                    AvailabilityEvent.event_type == "restock",
                )
            )
        ).scalar_one()
        values = dict(
            hotel_id=hotel_id,
            channel=channel,
            stay_date=stay_date,
            as_of_scan_run_id=scan_run_id,
            days_to_arrival=m.days_to_arrival,
            pickup_24h=m.pickup_24h,
            velocity_3d=m.velocity_3d,
            sold_out_at=sold_out_at,
            restocked_at=restocked_at,
            min_price=m.min_price,
            min_refundable_price=m.min_refundable_price,
            currency=m.currency,
            price_change_7d_pct=m.price_change_7d_pct,
            availability_status=str(m.availability_status),
            exact_rooms_left=m.exact_rooms_left,
            exact_share=m.exact_share,
            last_observed_at=m.last_observed_at,
            stale_since=m.stale_since,
        )
        stmt = insert(HotelDateMetric).values(**values)
        # Chặn ở SQL: hai job analytics chạy song song không để run cũ đè run mới hơn
        # (kiểm tra ở Python phía trên chỉ để khỏi tính vô ích).
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                HotelDateMetric.hotel_id,
                HotelDateMetric.channel,
                HotelDateMetric.stay_date,
            ],
            set_={k: v for k, v in values.items() if k not in ("hotel_id", "channel", "stay_date")},
            where=HotelDateMetric.last_observed_at <= stmt.excluded.last_observed_at,
        )
        result = await self._s.execute(stmt)
        return (result.rowcount or 0) > 0

    async def _cross_channel(
        self, scan_run_id: int, hotel_id: int, channel: str, report: AnalyticsReport
    ) -> None:
        """Sự kiện chéo kênh cho các đêm của run này (cần ≥2 kênh có metric)."""
        rows = (
            (
                await self._s.execute(
                    select(HotelDateMetric).where(
                        HotelDateMetric.hotel_id == hotel_id,
                        HotelDateMetric.stay_date.in_(
                            select(Probe.stay_date).where(
                                Probe.scan_run_id == scan_run_id, Probe.hotel_id == hotel_id
                            )
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        # Parity (D11) chỉ có nghĩa với khách sạn mà ít nhất một tenant theo dõi là "của bạn":
        # giá đối thủ lệch giữa kênh là chuyện thường, sinh sự kiện cho mọi khách sạn chỉ gây nhiễu.
        is_own = (
            await self._s.execute(
                select(TenantHotel.hotel_id)
                .where(
                    TenantHotel.hotel_id == hotel_id,
                    TenantHotel.role == "self",
                    TenantHotel.active.is_(True),
                )
                .limit(1)
            )
        ).first() is not None
        by_date: dict[date, list[HotelDateMetric]] = defaultdict(list)
        for m in rows:
            by_date[m.stay_date].append(m)
        run_times = [m.last_observed_at for m in rows if m.channel == channel]
        if not run_times:
            return
        # Các run cùng mốc chốt lệch giờ: mỗi lần một kênh xong, đánh giá lại mọi kênh có quan sát
        # trong cùng mốc (FRESH_FOR) và gắn sự kiện cho đúng kênh rẻ nhất / kênh đóng bán, bất kể
        # kênh nào xong trước. Không lặp lại trong 24h (mốc theo giờ quan sát, không theo DB).
        seen: dict[tuple[date, str], list[datetime]] = defaultdict(list)
        for r in await self._s.execute(
            select(
                AvailabilityEvent.stay_date,
                AvailabilityEvent.event_type,
                AvailabilityEvent.channel,
                AvailabilityEvent.observed_at,
            ).where(
                AvailabilityEvent.hotel_id == hotel_id,
                AvailabilityEvent.event_type.in_(["parity_gap", "channel_closed"]),
                AvailabilityEvent.stay_date.in_(list(by_date)),
                AvailabilityEvent.scan_run_id != scan_run_id,
            )
        ):
            key = "parity_gap" if r[1] == "parity_gap" else f"channel_closed:{r[2]}"
            seen[(r[0], key)].append(r[3])
        # Hết phòng *mới* (sự kiện sold_out) của mọi kênh trong cùng mốc: chỉ sự kiện quan sát trong
        # FRESH_FOR quanh lượt này. Kênh đã hết từ mốc trước và vẫn hết không phải "vừa đóng".
        new_sold_out: dict[tuple[date, str], list[datetime]] = defaultdict(list)
        for r in await self._s.execute(
            select(
                AvailabilityEvent.stay_date,
                AvailabilityEvent.channel,
                AvailabilityEvent.observed_at,
            ).where(
                AvailabilityEvent.hotel_id == hotel_id,
                AvailabilityEvent.event_type == "sold_out",
                AvailabilityEvent.room_type_id.is_(None),
                AvailabilityEvent.stay_date.in_(list(by_date)),
                AvailabilityEvent.observed_at >= min(run_times) - FRESH_FOR,
            )
        ):
            new_sold_out[(r[0], r[1])].append(r[2])
        tax_flags = await self._tax_inclusive_flags(hotel_id, rows) if is_own else {}

        def recently(stay: date, key: str, now: datetime) -> bool:
            return any(now - timedelta(hours=24) <= t <= now for t in seen.get((stay, key), []))

        def just_sold_out(stay: date, ch: str, now: datetime) -> bool:
            return any(abs(now - t) <= FRESH_FOR for t in new_sold_out.get((stay, ch), []))

        for stay_date, metrics in by_date.items():
            views = [
                ChannelView(
                    channel=m.channel,
                    status=m.availability_status,
                    min_price=m.min_price,
                    observed_at=m.last_observed_at,
                    min_refundable_price=m.min_refundable_price,
                    currency=m.currency,
                    tax_inclusive=tax_flags.get((stay_date, m.channel)),
                )
                for m in sorted(metrics, key=lambda m: m.channel)
            ]
            current = next((v for v in views if v.channel == channel), None)
            if current is None:
                continue
            now = current.observed_at
            fresh = [v for v in views if abs(now - v.observed_at) <= FRESH_FOR]
            if len(fresh) < 2:
                continue
            drafts: list[tuple[str, EventDraft]] = []
            for v in fresh:
                if not just_sold_out(stay_date, v.channel, now) or recently(
                    stay_date, f"channel_closed:{v.channel}", now
                ):
                    continue
                d = channel_closed(v, [o for o in fresh if o is not v], now)
                if d is not None:
                    drafts.append((v.channel, d))
            if is_own and not recently(stay_date, "parity_gap", now):
                # Cơ sở so có thể khác theo cặp kênh (gói huỷ miễn phí / giá gồm thuế), nên thử
                # từng kênh làm "kênh rẻ": tối đa một kênh rẻ hơn mọi kênh còn lại ≥ ngưỡng.
                for v in fresh:
                    d = parity_gap(v, [o for o in fresh if o is not v], now)
                    if d is not None:
                        drafts.append((v.channel, d))
                        break
            for event_channel, d in drafts:
                await self._insert_event(scan_run_id, hotel_id, event_channel, stay_date, now, d)
                EVENTS_TOTAL.labels(str(d.event_type)).inc()
                report.events += 1

    async def _tax_inclusive_flags(
        self, hotel_id: int, metrics: list[HotelDateMetric]
    ) -> dict[tuple[date, str], bool | None]:
        """Cờ "mọi gói đã gồm thuế phí" của lần quan sát mới nhất mỗi (đêm, kênh), đọc từ
        `room_snapshots.rates` của probe đó (metric không lưu cờ này). Thiếu → None."""
        keys = {
            (m.stay_date, m.channel, m.last_observed_at)
            for m in metrics
            if m.availability_status == "available"
        }
        if not keys:
            return {}
        rows = await self._s.execute(
            select(
                RoomSnapshot.stay_date,
                RoomSnapshot.channel,
                RoomSnapshot.scanned_at,
                RoomSnapshot.rates,
            ).where(
                RoomSnapshot.hotel_id == hotel_id,
                RoomSnapshot.stay_date.in_(sorted({k[0] for k in keys})),
                RoomSnapshot.scanned_at.in_(sorted({k[2] for k in keys})),
            )
        )
        flags: dict[tuple[date, str], bool | None] = {}
        for stay, ch, at, rates in rows:
            if (stay, ch, at) not in keys:
                continue
            room_flag = rates_tax_inclusive(rates or [])
            prev = flags.get((stay, ch), True)
            flags[(stay, ch)] = None if prev is None or room_flag is None else (prev and room_flag)
        return flags
