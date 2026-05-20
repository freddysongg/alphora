"""Lazy registry for per-source rate limiters.

Source clients call `get_rate_limiter(name=..., rate_per_second=..., burst=...)`
on each request rather than constructing a module-level limiter at import.
The registry caches the constructed limiter by `name`, so subsequent requests
share state across calls within the process.

Workers can call `configure_redis(redis_client)` at boot to install a shared
Redis client; the call clears the cache so the next `get_rate_limiter` call
returns a `RedisTokenBucket`. Subsequent in-process callers (the API process,
which never sets a Redis client) keep using `LocalTokenBucket` and remain
unaffected.

This module is process-local. Multiple processes (API + worker pool) each
have their own registry; only the worker process opts into Redis.
"""
from __future__ import annotations

import threading

from redis.asyncio import Redis

from app.services.source_clients._rate_limit import (
    RateLimiterProtocol,
    make_rate_limiter,
)
from app.services.source_clients._request_cache import RequestCache

_lock = threading.Lock()
_cache: dict[str, RateLimiterProtocol] = {}
_redis_client: Redis | None = None
_request_cache: RequestCache | None = None


def configure_redis(redis_client: Redis | None) -> None:
    """Install a Redis client into the registry.

    Clears the cached limiters so subsequent `get_rate_limiter` calls
    construct a `RedisTokenBucket` (or a `LocalTokenBucket` when the
    argument is `None`). Idempotent: passing the same value twice is a
    no-op after the cache is cleared.
    """
    global _redis_client
    with _lock:
        _redis_client = redis_client
        _cache.clear()


def get_rate_limiter(
    *,
    name: str,
    rate_per_second: float,
    burst: int,
) -> RateLimiterProtocol:
    """Return the cached limiter for `name`, lazily constructing on miss."""
    with _lock:
        existing = _cache.get(name)
        if existing is not None:
            return existing
        limiter = make_rate_limiter(
            name=name,
            rate_per_second=rate_per_second,
            burst=burst,
            redis_client=_redis_client,
        )
        _cache[name] = limiter
        return limiter


def install_request_cache(cache: RequestCache | None) -> None:
    """Install a process-wide request cache (None to disable).

    Used by the worker to opt into the 5-minute same-context cache window
    for source-client GET responses. The API process never installs one.
    """
    global _request_cache
    with _lock:
        _request_cache = cache


def get_request_cache() -> RequestCache | None:
    with _lock:
        return _request_cache


def reset_registry() -> None:
    """Clear all cached limiters, the installed Redis client, and the cache.

    Test-only helper: production code should call `configure_redis(None)` /
    `install_request_cache(None)` instead, but the test suite needs to
    fully tear down state between suites.
    """
    global _redis_client, _request_cache
    with _lock:
        _redis_client = None
        _request_cache = None
        _cache.clear()


__all__ = [
    "configure_redis",
    "get_rate_limiter",
    "get_request_cache",
    "install_request_cache",
    "reset_registry",
]
