import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Asyncio token-bucket rate limiter.

    Bucket starts full at `burst` tokens and refills at `rate_per_second` continuously.
    `acquire()` deducts one token; if none available, it sleeps the minimum interval
    needed for a token to arrive, then deducts.
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
