"""Thống kê giá danh sách và hàng đợi job quét danh sách (thuần)."""

from decimal import Decimal
from typing import Any

from arq.worker import get_kwargs

from app.marketscan.stats import histogram, percentile, price_stats
from app.scheduler.queue import ArqJobQueue
from app.worker.settings import MAX_TRIES, WorkerSettings


def test_percentile_interpolates_like_numpy() -> None:
    values = [Decimal(x) for x in (100, 200, 300, 400)]
    assert percentile(values, Decimal("0.5")) == Decimal("250")
    assert percentile(values, Decimal("0.25")) == Decimal("175")
    assert percentile([Decimal(7)], Decimal("0.75")) == Decimal(7)
    assert percentile([], Decimal("0.5")) is None


def test_histogram_buckets_cover_all_prices() -> None:
    buckets = histogram([Decimal(x) for x in (350_000, 500_000, 999_999, 2_500_000, 12_000_000)])
    assert len(buckets) == 8
    assert (buckets[0].lo, buckets[0].hi, buckets[0].count) == (0, 500_000, 1)
    assert buckets[1].count == 2  # 500k (biên dưới thuộc khoảng) và 999.999
    assert buckets[4].count == 1  # 2–3 triệu
    assert (buckets[-1].lo, buckets[-1].hi, buckets[-1].count) == (10_000_000, None, 1)
    assert sum(b.count for b in buckets) == 5


def test_price_stats() -> None:
    stats = price_stats([Decimal(x) for x in (1_000_000, 2_000_000, 1_500_001)])
    assert stats.count == 3
    assert stats.avg == Decimal("1500000")
    assert stats.median == Decimal("1500001")
    assert (stats.min, stats.max) == (Decimal(1_000_000), Decimal(2_000_000))
    assert stats.p25 == Decimal("1250001") and stats.p75 == Decimal("1750001")
    empty = price_stats([])
    assert empty.count == 0 and empty.avg is None and sum(b.count for b in empty.histogram) == 0


class _Redis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], str | None]] = []
        self.job_ids: list[str | None] = []

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((function, args, kwargs.get("_queue_name")))
        self.job_ids.append(kwargs.get("_job_id"))


async def test_market_list_job_goes_to_channel_queue_with_round_job_id() -> None:
    redis = _Redis()
    queue = ArqJobQueue(redis)  # type: ignore[arg-type]
    await queue.enqueue_market_list(7, "booking", "2026-10-02", 3, 1790924262)
    await queue.enqueue_market_list(7, "booking")
    assert redis.calls == [
        ("scan_market_list", (7, "2026-10-02", 3, 1790924262), "arq:queue:collector:booking"),
        ("scan_market_list", (7, None, 0, None), "arq:queue:collector:booking"),
    ]
    # Mã job cố định theo (khu vực, vòng, đêm): đẩy trùng (bù chuỗi) bị arq bỏ qua.
    assert redis.job_ids == ["mlist:7:1790924262:3", None]
    assert get_kwargs(WorkerSettings).get("queue_name") == "arq:queue:collector:booking"


def test_collector_functions_have_their_own_max_tries() -> None:
    tries = {f.name: f.max_tries for f in WorkerSettings.functions}  # type: ignore[attr-defined]
    # probe_hotel coi lần thử thứ MAX_TRIES là lần cuối: arq phải dừng đúng lần đó.
    assert tries == {
        "probe_hotel": MAX_TRIES,
        "verify_listing": 3,
        "scan_market_list": 1,
    }
