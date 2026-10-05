from app.collector.ratelimit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


async def test_first_call_does_not_wait() -> None:
    ft = FakeTime()
    rl = RateLimiter(
        min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0
    )
    await rl.wait("s1")
    assert ft.sleeps == []


async def test_second_call_waits_remaining_interval() -> None:
    ft = FakeTime()
    rl = RateLimiter(
        min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0
    )
    await rl.wait("s1")
    ft.t += 0.5
    await rl.wait("s1")
    assert ft.sleeps == [1.5]


async def test_jitter_added() -> None:
    ft = FakeTime()
    rl = RateLimiter(
        min_interval=2.0, jitter=1.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.5
    )
    await rl.wait("s1")
    await rl.wait("s1")
    assert ft.sleeps == [2.5]


async def test_keys_are_independent() -> None:
    ft = FakeTime()
    rl = RateLimiter(
        min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0
    )
    await rl.wait("s1")
    await rl.wait("s2")
    assert ft.sleeps == []


async def test_forget_drops_key_so_table_does_not_grow_with_retired_sessions() -> None:
    ft = FakeTime()
    rl = RateLimiter(
        min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0
    )
    for sid in ("s1", "s2", "s3"):
        await rl.wait(sid)
    rl.forget("s1")
    rl.forget("s2")
    rl.forget("missing")  # không có: không lỗi
    assert set(rl._last) == {"s3"}
    await rl.wait("s1")  # key đã quên: như lần đầu, không chờ
    assert ft.sleeps == []
    await rl.wait("s3")
    assert ft.sleeps == [2.0]
