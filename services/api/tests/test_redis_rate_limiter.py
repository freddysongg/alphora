import asyncio

import fakeredis.aioredis
import pytest

from app.services.source_clients._rate_limit import (
    LocalTokenBucket,
    RateLimiter,
    RedisTokenBucket,
    make_rate_limiter,
)


def test_rate_limiter_alias_points_at_local_token_bucket() -> None:
    assert RateLimiter is LocalTokenBucket


def test_make_rate_limiter_returns_local_bucket_without_redis() -> None:
    limiter = make_rate_limiter(name="t", rate_per_second=1.0, burst=2)
    assert isinstance(limiter, LocalTokenBucket)


def test_make_rate_limiter_returns_redis_bucket_with_client() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    limiter = make_rate_limiter(
        name="t", rate_per_second=1.0, burst=2, redis_client=redis
    )
    assert isinstance(limiter, RedisTokenBucket)


@pytest.mark.asyncio
async def test_redis_token_bucket_first_burst_does_not_sleep() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        await asyncio.sleep(0)

    bucket = RedisTokenBucket(
        name="test",
        rate_per_second=1.0,
        burst=3,
        redis_client=redis,
        sleep=fake_sleep,
    )
    for _ in range(3):
        await bucket.acquire()
    assert sleeps == []


@pytest.mark.asyncio
async def test_redis_token_bucket_sleeps_when_bucket_empty() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    fake_now = [1000.0]

    def fake_clock() -> float:
        return fake_now[0]

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake_now[0] += seconds

    bucket = RedisTokenBucket(
        name="test_sleep",
        rate_per_second=2.0,
        burst=2,
        redis_client=redis,
        clock=fake_clock,
        sleep=fake_sleep,
    )
    await bucket.acquire()
    await bucket.acquire()
    await bucket.acquire()
    assert sleeps
    assert sleeps[0] == pytest.approx(0.5, rel=1e-6)


class _NaturalYieldingRedis:
    """Wraps a redis client so top-level GETs yield to the event loop.

    Mirrors real Redis where each command is a network round-trip that forces an
    async yield. Pipeline operations remain atomic (no yields between them)
    because real Redis executes pipelines as a single round-trip. Used to drive
    the read-before-WATCH race deterministically in fakeredis (which otherwise
    runs every async call without yielding).
    """

    def __init__(self, inner: fakeredis.aioredis.FakeRedis) -> None:
        self._inner = inner

    async def get(self, *args: object, **kwargs: object) -> object:
        result = await self._inner.get(*args, **kwargs)  # type: ignore[arg-type]
        await asyncio.sleep(0)
        return result

    def pipeline(self, *args: object, **kwargs: object) -> object:
        return self._inner.pipeline(*args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_redis_token_bucket_concurrent_acquires_do_not_double_spend() -> None:
    """Two concurrent acquires on a 1-token shared bucket must serialize.

    Regression for the race where the read happens BEFORE WATCH: two workers
    can both read tokens=1, then sequentially run their WATCH+SET=0 pipelines.
    The second worker's WATCH starts AFTER the first worker's EXEC, so it never
    detects the prior change and silently overwrites with a stale-derived value.
    Both think they got a token; only one decrement is recorded.

    The fix puts the GET inside the WATCH window: either the post-WATCH GET
    sees the updated state, or the EXEC fails on WATCH and the loop retries.
    """
    inner = fakeredis.aioredis.FakeRedis()
    redis = _NaturalYieldingRedis(inner)
    fake_now = [1000.0]
    sleeps: list[float] = []

    def fake_clock() -> float:
        return fake_now[0]

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake_now[0] += seconds

    def build_bucket() -> RedisTokenBucket:
        return RedisTokenBucket(
            name="race",
            rate_per_second=10.0,
            burst=1,
            redis_client=redis,  # type: ignore[arg-type]
            clock=fake_clock,
            sleep=fake_sleep,
        )

    bucket_a = build_bucket()
    bucket_b = build_bucket()

    await asyncio.gather(bucket_a.acquire(), bucket_b.acquire())

    assert len(sleeps) == 1, f"expected exactly one sleep, got {sleeps}"


@pytest.mark.asyncio
async def test_redis_token_bucket_state_is_shared_across_instances() -> None:
    """Two limiter instances under the same name share Redis state."""
    redis = fakeredis.aioredis.FakeRedis()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        await asyncio.sleep(0)

    one = RedisTokenBucket(
        name="shared",
        rate_per_second=1.0,
        burst=2,
        redis_client=redis,
        sleep=fake_sleep,
    )
    two = RedisTokenBucket(
        name="shared",
        rate_per_second=1.0,
        burst=2,
        redis_client=redis,
        sleep=fake_sleep,
    )
    await one.acquire()
    await two.acquire()
    assert sleeps == []
    await one.acquire()
    assert sleeps
