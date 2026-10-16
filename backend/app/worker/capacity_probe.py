"""Đo số phòng Booking.com bán nhiều nhất trong một đêm: nguồn gợi ý "Số phòng"
(app/domain/capacity.py).

Lịch GraphQL `AvailabilityCalendar` với `nbRooms = N` trả lời cho cả cửa sổ đêm "khách sạn còn bán
được N phòng cùng lúc?" (app/worker/capacity_ladder.py). Số đêm còn giảm dần theo N, nên tìm nhị
phân được số N lớn nhất mà ít nhất một đêm còn bán. Đo trên các đêm XA (hôm nay + 60, 61 đêm): ít
người đặt nên gần với toàn bộ phần phòng khách sạn giao cho Booking. Kiểm live 16/10/2026 (cửa sổ
15/12 → 13/02): Meander 94 đơn vị (9 request), Reverie còn ở N = 100 (2 request).

Khoảng 9 request lịch mỗi lần đo khi không lỗi (N = 1, N = 100, rồi nhị phân). Lỗi GraphQL/5xx có
thể chỉ tạm thời (live: N = 75 lỗi 500, gọi lại thì còn 51 đêm) nên được hỏi lại một lần; bị chặn
hay lỗi mạng thì dừng ngay, không gửi thêm request. Dừng giữa chừng vẫn giữ cận dưới đã biết.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Listing, Tenant, TenantHotel
from app.domain.capacity import CAPACITY_CEILING
from app.domain.models import ListingRef
from app.logging import get_logger
from app.worker.listing_jobs import ListingJobDeps

log = get_logger(__name__)

WINDOW_OFFSET_DAYS = 60  # bắt đầu sau cửa sổ 61 đêm của lượt quét thường (thang nbRooms đã đo)
WINDOW_DAYS = 61
# Lúc đo lại, theo kết quả lần đo (cột listings.capacity_next_at).
REMEASURE_AFTER = timedelta(days=30)  # đo xong: số phòng ít đổi
NO_INVENTORY_RETRY = timedelta(days=7)  # cửa sổ xa chưa mở bán
INCOMPLETE_RETRY = timedelta(days=1)  # lịch lỗi/bị chặn giữa chừng
CATCH_UP_LIMIT = 20  # số listing tối đa mỗi lượt cron (mỗi job ~9 request lịch)
# Lỗi lịch có thể tạm thời (hỏi lại được): payload lỗi GraphQL ("Internal Server Error"), 5xx.
TRANSIENT_ERRORS = ("unexpected payload", "invalid json", "http 5")


class CalendarUnavailable(RuntimeError):
    """Lịch bị chặn / lỗi mạng / proxy: dừng đo ngay, không hỏi lại."""


@dataclass(frozen=True)
class CapacityMeasurement:
    units: int | None  # N lớn nhất còn bán ít nhất một đêm; None = không có phòng/không đo được
    capped: bool  # còn bán ở trần đo (CAPACITY_CEILING)
    complete: bool  # tìm xong (không dừng giữa chừng)
    requests: int


async def search_capacity(
    available_nights: Callable[[int], Awaitable[int | None]],
    ceiling: int = CAPACITY_CEILING,
    retries: int = 1,
) -> CapacityMeasurement:
    """`available_nights(n)`: số đêm còn bán ở nbRooms = n; None = lỗi tạm thời (hỏi lại tối đa
    `retries` lần); ném CalendarUnavailable = dừng ngay."""
    requests = 0
    lo: int | None = None  # còn bán ở `lo` (đã biết)

    async def ask(n: int) -> bool | None:
        nonlocal requests
        for _ in range(retries + 1):
            requests += 1
            nights = await available_nights(n)
            if nights is not None:
                return nights > 0
        return None

    try:
        first = await ask(1)
        if not first:  # lỗi (None) hoặc cửa sổ không còn phòng nào (False)
            return CapacityMeasurement(None, False, first is False, requests)
        lo = 1
        top = await ask(ceiling)  # khách sạn lớn: hai request là xong ("≥100")
        if top:
            return CapacityMeasurement(ceiling, True, True, requests)
        # Không còn ở `hi`. Trần lỗi cả hai lần (top None): không hỏi lại, tìm dưới trần; dồn tới
        # trần - 1 thì không phân biệt được "đúng 99" với "≥100" → chưa xong.
        hi = ceiling
        while hi - lo > 1:
            mid = (lo + hi) // 2
            answer = await ask(mid)
            if answer is None:
                return CapacityMeasurement(lo, False, False, requests)
            if answer:
                lo = mid
            else:
                hi = mid
        return CapacityMeasurement(lo, False, top is False or lo < ceiling - 1, requests)
    except CalendarUnavailable:
        return CapacityMeasurement(lo, False, False, requests)


def next_measure_at(m: CapacityMeasurement, now: datetime) -> datetime:
    if not m.complete:
        return now + INCOMPLETE_RETRY
    return now + (REMEASURE_AFTER if m.units else NO_INVENTORY_RETRY)


async def run_measure_capacity(deps: ListingJobDeps, listing_id: int, force: bool = False) -> str:
    """Đo một listing Booking đang quét. Mặc định giữ kết quả lớn nhất từng đo (không bao giờ
    giảm); `force` (operator đo lại một khách sạn) thay kết quả cũ khi đo xong."""
    now = deps.clock.now()
    async with deps.session_factory() as s:
        row = (
            await s.execute(
                select(Listing, Hotel)
                .join(Hotel, Hotel.id == Listing.hotel_id)
                .where(Listing.id == listing_id)
            )
        ).first()
        if row is None:
            return "missing"
        listing, hotel = row
        if listing.status != "active":
            return "inactive"
        due = listing.capacity_next_at
        if not force and due is not None and now < due:
            return "fresh"
        ref = ListingRef(
            hotel_id=hotel.id,
            channel=listing.channel,
            listing_key=listing.listing_key,
            url=listing.url,
            country_code=hotel.country_code,
            external_id=listing.external_id,
        )
    start = now.date() + timedelta(days=WINDOW_OFFSET_DAYS)

    async def available_nights(n: int) -> int | None:
        try:
            cal = await deps.collector.fetch_calendar(ref, start, WINDOW_DAYS, n, rooms=n)
        except Exception as exc:  # noqa: BLE001 — hết ngân sách, phiên/proxy lỗi: dừng đo
            log.warning("capacity_probe_raised", listing_id=listing_id, rooms=n, error=repr(exc))
            raise CalendarUnavailable(repr(exc)) from exc
        if not cal.ok:
            log.warning("capacity_probe_error", listing_id=listing_id, rooms=n, error=cal.error)
            if (cal.error or "").startswith(TRANSIENT_ERRORS):
                return None
            raise CalendarUnavailable(cal.error or "error")
        if not cal.days:  # trả lời rỗng: chưa biết, không coi là hết phòng
            return None
        return sum(1 for d in cal.days if d.available)

    m = await search_capacity(available_nights)
    values: dict[str, object] = {"capacity_next_at": next_measure_at(m, now)}
    if m.complete:
        values["capacity_checked_at"] = now
    if force and m.complete:
        values |= {"capacity_max": m.units, "capacity_capped": m.capped}
    else:
        # Cập nhật nguyên tử như analytics (`_update_rooms_max_seen`): không ghi đè số lớn hơn
        # mà job khác vừa ghi.
        if m.units:
            values["capacity_max"] = func.greatest(func.coalesce(Listing.capacity_max, 0), m.units)
        if m.capped:
            values["capacity_capped"] = True
    async with deps.session_factory() as s:
        await s.execute(update(Listing).where(Listing.id == listing_id).values(**values))
        if m.units:
            # Cũng là "Booking từng mở bán ≥N phòng/đêm" (lượt quét thường chỉ thấy các đêm gần).
            await s.execute(
                update(Listing)
                .where(
                    Listing.id == listing_id,
                    func.coalesce(Listing.rooms_max_seen, 0) < m.units,
                )
                .values(rooms_max_seen=m.units, rooms_max_seen_at=now)
            )
        await s.commit()
    log.info(
        "capacity_measured",
        listing_id=listing_id,
        units=m.units,
        capped=m.capped,
        complete=m.complete,
        requests=m.requests,
        force=force,
    )
    if not m.complete:
        return "incomplete"
    return "measured" if m.units else "no_inventory"


async def due_capacity_listings(
    s: AsyncSession,
    now: datetime,
    *,
    limit: int = CATCH_UP_LIMIT,
    include_fresh: bool = False,
) -> list[tuple[int, str]]:
    """(listing_id, channel) cần đo: listing đang quét của khách sạn có tenant theo dõi mà CHƯA có
    "Số phòng" (còn cần gợi ý), chưa đo lần nào hoặc đã tới `capacity_next_at`; chưa đo trước.
    `include_fresh`: bỏ qua lịch đo lại (operator ép đo)."""
    tracked = (
        select(TenantHotel.hotel_id)
        .join(Tenant, Tenant.id == TenantHotel.tenant_id)
        .where(TenantHotel.active.is_(True), Tenant.active.is_(True))
    )
    stmt = (
        select(Listing.id, Listing.channel)
        .join(Hotel, Hotel.id == Listing.hotel_id)
        .where(
            Listing.status == "active",
            Listing.hotel_id.in_(tracked),
            Hotel.rooms_total.is_(None),
        )
    )
    if not include_fresh:
        stmt = stmt.where(or_(Listing.capacity_next_at.is_(None), Listing.capacity_next_at <= now))
    rows = await s.execute(
        stmt.order_by(Listing.capacity_next_at.asc().nulls_first(), Listing.id).limit(limit)
    )
    return [(int(r[0]), str(r[1])) for r in rows]
