"""Opt-in integration tests for `RedisTokenBucket` against a real Redis.

These tests are skipped unless `REDIS_URL` is set. They are not exercised in
default CI runs because no production caller currently passes `redis_client=`
to `make_rate_limiter` — the worker pool wires up the local in-process bucket.
Run with `REDIS_URL=redis://localhost:6379 uv run pytest -m real_redis` once
the worker layer plumbs a real Redis client through.

The unit tests in `test_redis_rate_limiter.py` already exercise the WATCH/MULTI
algorithm deterministically against `fakeredis`. The value here is confirming
that the same code path behaves correctly against the real Redis server,
guarding against future fakeredis-vs-real divergence on transactional
semantics.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from redis.asyncio import Redis

from app.services.source_clients._rate_limit import RedisTokenBucket

_REDIS_URL = os.environ.get("REDIS_URL")

pytestmark = [
    pytest.mark.real_redis,
    pytest.mark.skipif(
        _REDIS_URL is None,
        reason="set REDIS_URL to exercise the real-Redis rate-limiter tests",
    ),
]


@pytest.fixture()
async def redis_client():
    assert _REDIS_URL is not None
    client = Redis.from_url(_REDIS_URL, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture()
async def fresh_bucket_name(redis_client: Redis) -> str:
    name = f"test-real-{os.urandom(8).hex()}"
    yield name
    await redis_client.delete(f"alphora:rate-limit:{name}")


@pytest.mark.asyncio
async def test_real_redis_first_burst_does_not_sleep(
    redis_client: Redis, fresh_bucket_name: str
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    bucket = RedisTokenBucket(
        name=fresh_bucket_name,
        rate_per_second=1.0,
        burst=3,
        redis_client=redis_client,
        sleep=fake_sleep,
    )
    for _ in range(3):
        await bucket.acquire()
    assert sleeps == []


@pytest.mark.asyncio
async def test_real_redis_sleeps_when_bucket_empty(
    redis_client: Redis, fresh_bucket_name: str
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    bucket = RedisTokenBucket(
        name=fresh_bucket_name,
        rate_per_second=2.0,
        burst=1,
        redis_client=redis_client,
        sleep=fake_sleep,
    )
    await bucket.acquire()
    await bucket.acquire()
    assert len(sleeps) == 1
    assert sleeps[0] > 0.0


@pytest.mark.asyncio
async def test_real_redis_concurrent_acquires_do_not_double_spend(
    redis_client: Redis, fresh_bucket_name: str
) -> None:
    """Two concurrent acquires on a 1-token shared bucket must serialize.

    Against real Redis the network round-trip provides the same yielding
    behavior the fakeredis unit test fakes with `_NaturalYieldingRedis`, so
    this test exercises the WATCH/MULTI race for real.
    """
    sleeps: list[float] = []
    sleep_lock = asyncio.Lock()

    async def fake_sleep(seconds: float) -> None:
        async with sleep_lock:
            sleeps.append(seconds)

    def build_bucket() -> RedisTokenBucket:
        return RedisTokenBucket(
            name=fresh_bucket_name,
            rate_per_second=10.0,
            burst=1,
            redis_client=redis_client,
            sleep=fake_sleep,
        )

    bucket_a = build_bucket()
    bucket_b = build_bucket()
    await asyncio.gather(bucket_a.acquire(), bucket_b.acquire())

    assert len(sleeps) == 1, (
        f"expected exactly one sleep across both acquires, got {sleeps}"
    )
