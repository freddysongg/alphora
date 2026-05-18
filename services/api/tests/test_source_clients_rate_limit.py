import asyncio

import pytest


class _FakeClock:
    def __init__(self) -> None:
        self.now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingSleep:
    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


@pytest.fixture()
def fake_clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture()
def recording_sleep(fake_clock: _FakeClock) -> _RecordingSleep:
    return _RecordingSleep(fake_clock)


async def test_burst_does_not_sleep(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=2.0, burst=3, clock=fake_clock, sleep=recording_sleep
    )

    for _ in range(3):
        await limiter.acquire()

    assert recording_sleep.calls == []


async def test_acquire_after_burst_sleeps_one_token_interval(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=2.0, burst=1, clock=fake_clock, sleep=recording_sleep
    )

    await limiter.acquire()
    await limiter.acquire()

    assert recording_sleep.calls == [pytest.approx(0.5)]


async def test_tokens_refill_over_time(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=4.0, burst=1, clock=fake_clock, sleep=recording_sleep
    )

    await limiter.acquire()
    fake_clock.advance(0.25)
    await limiter.acquire()

    assert recording_sleep.calls == []


async def test_concurrent_acquires_serialize(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=10.0, burst=2, clock=fake_clock, sleep=recording_sleep
    )

    async def caller() -> None:
        await limiter.acquire()

    await asyncio.gather(caller(), caller(), caller(), caller())

    assert len(recording_sleep.calls) == 2
    for sleep_seconds in recording_sleep.calls:
        assert sleep_seconds == pytest.approx(0.1)


async def test_rate_limiter_rejects_invalid_config() -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    with pytest.raises(ValueError):
        RateLimiter(rate_per_second=0.0, burst=1)
    with pytest.raises(ValueError):
        RateLimiter(rate_per_second=1.0, burst=0)


def test_rate_limiter_uses_module_default_clock_and_sleep() -> None:
    import time

    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(rate_per_second=1.0, burst=1)

    assert limiter._clock is time.monotonic
    assert limiter._sleep is asyncio.sleep
