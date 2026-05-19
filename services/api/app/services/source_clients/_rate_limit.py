"""Source-client rate limiters with a local in-process fallback and a
Redis-backed variant for cross-process coordination.

`make_rate_limiter` picks between them based on whether a redis client is
provided. Source-client module-level rate limiters call the factory without
a redis client and get back a `LocalTokenBucket` (typed as `RateLimiter`
for backward compat). Workers can construct Redis-backed limiters at setup
time when `settings.redis_url` is configured.

The Redis path uses WATCH/MULTI for atomic refill+deduct rather than a Lua
script — `fakeredis` 2.35.1 does not support `EVAL`, and we want our tests
to run on the same code path as production.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import WatchError

_KEY_PREFIX = "alphora:rate-limit"


class RateLimiterProtocol(Protocol):
    async def acquire(self) -> None: ...


class LocalTokenBucket:
    """In-process asyncio token-bucket rate limiter.

    Bucket starts full at `burst` tokens and refills at `rate_per_second`
    continuously. `acquire()` deducts one token; if none available, it
    sleeps the minimum interval needed for a token to arrive, then deducts.
    """

    def __init__(
        self,
        *,
        rate_per_second: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0.0:
            raise ValueError("rate_per_second must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")

        self._rate_per_second = rate_per_second
        self._burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            needed = 1.0 - self._tokens
            wait_seconds = needed / self._rate_per_second
            await self._sleep(wait_seconds)
            self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed <= 0.0:
            return
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate_per_second)
        self._last_refill = now


RateLimiter = LocalTokenBucket


class RedisTokenBucket:
    """Redis-backed token bucket using WATCH/MULTI for atomic refill+deduct.

    State is stored as a JSON blob at `alphora:rate-limit:<name>` with two
    fields: `tokens` and `last_refill_ts`. On `acquire()`, the limiter
    optimistically reads, refills, and deducts under WATCH. If another
    writer mutated the key, the loop retries. When the bucket is empty,
    the call sleeps for the minimum refill interval before retrying.
    """

    def __init__(
        self,
        *,
        name: str,
        rate_per_second: float,
        burst: int,
        redis_client: Redis,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0.0:
            raise ValueError("rate_per_second must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")

        self._key = f"{_KEY_PREFIX}:{name}"
        self._rate_per_second = rate_per_second
        self._burst = float(burst)
        self._redis = redis_client
        self._clock = clock
        self._sleep = sleep

    async def acquire(self) -> None:
        while True:
            tokens, last_refill, now = await self._read_state()
            elapsed = max(0.0, now - last_refill)
            refilled = min(self._burst, tokens + elapsed * self._rate_per_second)
            if refilled >= 1.0:
                if await self._try_write(refilled - 1.0, now):
                    return
                continue
            wait_seconds = (1.0 - refilled) / self._rate_per_second
            await self._sleep(wait_seconds)

    async def _read_state(self) -> tuple[float, float, float]:
        raw = await self._redis.get(self._key)
        now = self._clock()
        if raw is None:
            return self._burst, now, now
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        state = json.loads(decoded)
        return float(state["tokens"]), float(state["last_refill_ts"]), now

    async def _try_write(self, new_tokens: float, now: float) -> bool:
        async with self._redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(self._key)
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.set(
                    self._key,
                    json.dumps({"tokens": new_tokens, "last_refill_ts": now}),
                )
                await pipe.execute()
                return True
            except WatchError:
                return False


def make_rate_limiter(
    *,
    name: str,
    rate_per_second: float,
    burst: int,
    redis_client: Redis | None = None,
) -> RateLimiterProtocol:
    """Construct a rate limiter, picking Local vs Redis based on `redis_client`.

    Source-client modules call this without a redis client at import time
    and get back a `LocalTokenBucket` (typed as `RateLimiter`). Workers
    that have a Redis connection can pass it in to coordinate across
    processes.
    """
    if redis_client is None:
        return LocalTokenBucket(rate_per_second=rate_per_second, burst=burst)
    return RedisTokenBucket(
        name=name,
        rate_per_second=rate_per_second,
        burst=burst,
        redis_client=redis_client,
    )


__all__ = [
    "LocalTokenBucket",
    "RateLimiter",
    "RateLimiterProtocol",
    "RedisTokenBucket",
    "make_rate_limiter",
]
