"""Đo số phòng Booking bán nhiều nhất trong một đêm (tìm nhị phân trên lịch nbRooms) và gợi ý
"Số phòng" (hàm thuần), cùng chỗ nối hàng đợi/worker."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from app.domain.capacity import CAPACITY_CEILING, rooms_suggestion, sells_beds
from app.worker.capacity_probe import CalendarUnavailable, search_capacity


def _meander(n: int) -> int:
    """Số đêm còn bán ở nbRooms = n, theo đo live 16/10/2026 (cửa sổ 61 đêm từ 15/12): còn ở 90
    (26 đêm), hết ở 100. Giả định trần thật 95."""
    table = {62: 61, 68: 58, 71: 55, 73: 51, 75: 51, 76: 49, 80: 44, 90: 26, 95: 3}
    if n > 95:
        return 0
    return next((v for k, v in sorted(table.items()) if n <= k), 0)


class Calendar:
    """Lịch giả: `answer(n)` = số đêm còn; `errors` = các nbRooms trả lỗi tạm thời (mỗi phần tử
    một lần); `blocked` = các nbRooms bị chặn (dừng đo)."""

    def __init__(
        self,
        answer: Callable[[int], int],
        errors: tuple[int, ...] = (),
        blocked: tuple[int, ...] = (),
    ) -> None:
        self.answer = answer
        self.errors = list(errors)
        self.blocked = blocked
        self.calls: list[int] = []

    async def __call__(self, n: int) -> int | None:
        self.calls.append(n)
        if n in self.blocked:
            raise CalendarUnavailable("blocked")
        if n in self.errors:
            self.errors.remove(n)
            return None
        return self.answer(n)


async def test_binary_search_finds_the_most_units_sold_in_one_night() -> None:
    cal = Calendar(_meander)
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete) == (95, False, True)
    # N = 1 (cửa sổ có hàng), N = 100 (trần), rồi nhị phân: 9 request cho cả khách sạn.
    assert cal.calls[:2] == [1, CAPACITY_CEILING]
    assert m.requests == len(cal.calls) == 9


async def test_available_at_the_ceiling_is_a_lower_bound() -> None:
    """Reverie 286 phòng: còn ở N = 100 (46/61 đêm) → chỉ biết "≥100", 2 request."""
    cal = Calendar(lambda n: 46)
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete, m.requests) == (100, True, True, 2)


async def test_window_without_inventory_measures_nothing() -> None:
    cal = Calendar(lambda n: 0)
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete, cal.calls) == (None, False, True, [1])


async def test_transient_error_is_retried_not_read_as_sold_out() -> None:
    """Live: Meander N = 75 trả lỗi 500 một lần, gọi lại thì còn 51 đêm."""
    plain = await search_capacity(Calendar(_meander))
    flaky = Calendar(_meander, errors=(75,))
    m = await search_capacity(flaky)
    assert (m.units, m.complete) == (plain.units, True)
    assert flaky.calls.count(75) == 2 and m.requests == plain.requests + 1


async def test_persistent_error_keeps_the_lower_bound_found_so_far() -> None:
    cal = Calendar(_meander, errors=(75, 75))
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete) == (50, False, False)


async def test_blocked_calendar_stops_at_once_without_retry() -> None:
    """Bị chặn/lỗi mạng: không gửi thêm request nào (kể cả hỏi lại)."""
    cal = Calendar(_meander, blocked=(75,))
    m = await search_capacity(cal)
    assert (m.units, m.complete) == (50, False)
    assert cal.calls == [1, CAPACITY_CEILING, 50, 75]
    first = Calendar(_meander, blocked=(1,))
    m = await search_capacity(first)
    assert (m.units, m.complete, first.calls) == (None, False, [1])


async def test_error_on_the_first_rung_measures_nothing() -> None:
    m = await search_capacity(Calendar(_meander, errors=(1, 1)))
    assert (m.units, m.complete, m.requests) == (None, False, 2)


async def test_error_at_the_ceiling_still_finds_a_smaller_maximum() -> None:
    cal = Calendar(_meander, errors=(CAPACITY_CEILING, CAPACITY_CEILING))
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete) == (95, False, True)
    assert cal.calls.count(CAPACITY_CEILING) == 2  # không hỏi lại trần


async def test_ceiling_error_with_a_maximum_just_below_is_incomplete() -> None:
    """Trần lỗi, mọi nấc dưới đều còn: không phân biệt được "đúng 99" với "≥100"."""
    cal = Calendar(lambda n: 1, errors=(CAPACITY_CEILING, CAPACITY_CEILING))
    m = await search_capacity(cal)
    assert (m.units, m.capped, m.complete) == (CAPACITY_CEILING - 1, False, False)
    assert cal.calls.count(CAPACITY_CEILING) == 2


def test_dorm_beds_are_detected_from_booking_room_type_names() -> None:
    meander = [
        "Bed in 8-Bed Mixed Dormitory Room",
        "Deluxe Double Room",
        "Single Bed in Female Dormitory Room",
    ]
    assert sells_beds(meander)
    assert sells_beds(["Bed in 6-Bed Dorm"]) and sells_beds(["Capsule Bed"])
    assert sells_beds(["Giường trong phòng ngủ tập thể 6 người"])
    for room in (
        "Deluxe King Room High Floor",
        "Bedroom Suite",
        "Sofa Bed in Living Room",
        "Extra Bed in the Room",
        "Dormer Attic Room",
        "Family Room with Bunk Bed",
    ):
        assert not sells_beds([room]), room
    assert not sells_beds([])


def test_suggestion_needs_a_far_window_with_rooms() -> None:
    """Chỉ có sàn của các đêm gần (Reverie 62 trong khi đo đêm xa ≥100): không gợi ý; đo xong mà
    cửa sổ xa chưa có phòng cũng vậy."""
    assert rooms_suggestion(None, False, 62, measured=False, includes_beds=False) is None
    assert rooms_suggestion(None, False, 62, measured=True, includes_beds=False) is None
    assert rooms_suggestion(74, False, 62, measured=False, includes_beds=False) is None


def test_exact_measurement_is_confirmable() -> None:
    s = rooms_suggestion(74, False, 54, measured=True, includes_beds=False)
    assert s is not None and (s.rooms, s.lower_bound, s.capped) == (74, False, False)
    assert s.confirmable


def test_dorm_beds_are_shown_but_not_confirmable() -> None:
    """Meander: 94 đơn vị Booking gồm cả giường, 42 phòng thật."""
    s = rooms_suggestion(94, False, 54, measured=True, includes_beds=True)
    assert s is not None and (s.rooms, s.includes_beds, s.confirmable) == (94, True, False)


def test_more_seen_than_measured_is_only_a_lower_bound() -> None:
    """Lượt quét thường từng thấy nhiều hơn kết quả đo (VD khách sạn giới hạn số phòng mỗi lần
    đặt): số lớn hơn, nhưng chỉ là cận dưới."""
    s = rooms_suggestion(5, False, 30, measured=True, includes_beds=False)
    assert s is not None and (s.rooms, s.lower_bound, s.capped, s.confirmable) == (
        30,
        True,
        False,
        False,
    )


def test_suggestion_at_or_above_the_ceiling_is_capped() -> None:
    s = rooms_suggestion(100, True, 95, measured=True, includes_beds=False)
    assert s is not None and (s.rooms, s.capped, s.lower_bound, s.confirmable) == (
        100,
        True,
        True,
        False,
    )
    # Sàn trang (Σ loại phòng "≥10") vượt trần lịch: vẫn chỉ là cận dưới.
    s = rooms_suggestion(80, False, 110, measured=True, includes_beds=False)
    assert s is not None and (s.rooms, s.capped) == (110, True)


class Redis:
    def __init__(self) -> None:
        self.jobs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> None:
        self.jobs.append((args, kwargs))


async def test_capacity_jobs_go_to_the_booking_collector_queue() -> None:
    from app.scheduler.queue import ArqJobQueue

    redis = Redis()
    queue = ArqJobQueue(redis)  # type: ignore[arg-type]
    await queue.enqueue_capacity(7, "booking", defer_by=timedelta(minutes=4))
    await queue.enqueue_capacity(7, "booking", force=True)
    (args, kw), (fargs, fkw) = redis.jobs
    assert args == ("measure_capacity", 7, False) and fargs == ("measure_capacity", 7, True)
    assert kw["_queue_name"] == fkw["_queue_name"] == "arq:queue:collector:booking"
    assert kw["_job_id"].startswith("capacity:7:") and fkw["_job_id"] is None
    assert kw["_defer_by"] == timedelta(minutes=4)


async def test_worker_skips_measurement_while_the_channel_is_paused() -> None:
    from app.worker.settings import measure_capacity

    class Pauses:
        async def is_paused(self, channel: str) -> bool:
            return channel == "booking"

    ctx = {"pauses": Pauses(), "channel": "booking", "listing_deps": None}
    assert await measure_capacity(ctx, 7) == "paused"
