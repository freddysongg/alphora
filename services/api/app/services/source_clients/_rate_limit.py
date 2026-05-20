"""Source-client rate limiters with a local in-process fallback and a
Redis-backed variant for cross-process coordination.

`make_rate_limiter` picks between them based on whether a redis client is
provided. Source-client module-level rate limiters call the factory without
a redis client and get back a `LocalTokenBucket` (typed as `RateLimiter`
for backward compat). Workers can construct Redis-backed limiters at setup
time when `settings.redis_url` is configured.

The Redis path uses WATCH/MULTI for atomic refill+deduct rather than a Lua
script — `fakeredis` 2.35.1 does not support `EVAL`, and we want our tests
to run on the same code path as production. Both the GET and the SET live
inside the watched window so a write derived from a stale read either sees
the new value or fails the EXEC and retries.
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
    fields: `tokens` and `last_refill_ts`. `acquire()` opens a WATCH-aware
    pipeline, reads the state INSIDE the watched window, computes the refill,
    and writes the decremented state in the same transaction. WATCH guarantees
    the EXEC fails if any other writer mutated the key after our read; on
    failure the loop retries. When the bucket is empty, the call releases the
    WATCH, sleeps for the minimum refill interval, and retries.
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
            wait_seconds = await self._attempt_acquire()
            if wait_seconds is None:
                return
            if wait_seconds > 0.0:
                await self._sleep(wait_seconds)

    async def _attempt_acquire(self) -> float | None:
        """Run one watched read+refill+deduct cycle.

        Returns `None` when a token was acquired, the required wait duration
        when the bucket is empty, or `0.0` to indicate the caller should retry
        immediately because the EXEC failed under WATCH contention.
        """
        async with self._redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(self._key)
                raw = await pipe.get(self._key)
                now = self._clock()
                tokens, last_refill = self._parse_state(raw, now)
                elapsed = max(0.0, now - last_refill)
                refilled = min(
                    self._burst, tokens + elapsed * self._rate_per_second
                )
                if refilled >= 1.0:
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.set(
                        self._key,
                        json.dumps(
                            {"tokens": refilled - 1.0, "last_refill_ts": now}
                        ),
                    )
                    await pipe.execute()
                    return None
                await pipe.unwatch()  # type: ignore[no-untyped-call]
                return (1.0 - refilled) / self._rate_per_second
            except WatchError:
                return 0.0

    def _parse_state(
        self, raw: bytes | str | None, now: float
    ) -> tuple[float, float]:
        if raw is None:
            return self._burst, now
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        state = json.loads(decoded)
        return float(state["tokens"]), float(state["last_refill_ts"])


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
