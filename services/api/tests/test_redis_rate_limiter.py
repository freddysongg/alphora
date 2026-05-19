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
