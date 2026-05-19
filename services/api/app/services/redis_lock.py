"""Redis-backed budget evaluation lock with in-process fallback.

The lock serializes `LlmClient._evaluate_and_persist` across concurrent calls
within the same `run_id` so sector fan-out cannot race the prior-sum +
decision + persist sequence under bounded concurrency.

The async context manager protocol matches the standard library, so callers
can use either implementation interchangeably:

    async with lock_factory(run_id):
        ...
"""
from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from types import TracebackType
from typing import ClassVar, Protocol
from uuid import UUID

from redis.asyncio import Redis

_LOCK_TTL_SECONDS = 30
_RETRY_INITIAL_SECONDS = 0.005
_RETRY_MAX_SECONDS = 0.25
_KEY_PREFIX = "alphora:budget-lock"


class BudgetLockProtocol(Protocol):
    async def __aenter__(self) -> BudgetLockProtocol: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


BudgetLockFactory = Callable[[UUID | None], BudgetLockProtocol]


class LocalBudgetLock:
    """asyncio.Lock-backed lock keyed on a single in-process registry.

    Used by tests and any deployment without Redis. Lock identity is keyed
    on the `run_id`; the global "None" key serializes all run-less calls.
    """

    _registry: ClassVar[dict[str, asyncio.Lock]] = {}
    _registry_guard: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, run_id: UUID | None) -> None:
        self._key = "__global__" if run_id is None else str(run_id)
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> LocalBudgetLock:
        async with LocalBudgetLock._registry_guard:
            existing = LocalBudgetLock._registry.get(self._key)
            if existing is None:
                existing = asyncio.Lock()
                LocalBudgetLock._registry[self._key] = existing
            self._lock = existing
        await self._lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._lock is not None and self._lock.locked():
            self._lock.release()
            self._lock = None


class RedisBudgetLock:
    """Redis SETNX-based lock keyed on `run_id` with TTL fallback.

    Uses `SET key value NX EX ttl` to acquire. On contention, retries with
    exponential backoff up to `_RETRY_MAX_SECONDS`. Release uses a
    WATCH/MULTI transaction so the key is only deleted when its current
    value still matches the holder's token, avoiding accidental release of
    a successor lock acquired after TTL expiry.
    """

    def __init__(self, redis: Redis, run_id: UUID | None) -> None:
        self._redis = redis
        key_suffix = "__global__" if run_id is None else str(run_id)
        self._key = f"{_KEY_PREFIX}:{key_suffix}"
        self._token = secrets.token_hex(16).encode("utf-8")

    async def __aenter__(self) -> RedisBudgetLock:
        delay = _RETRY_INITIAL_SECONDS
        while True:
            acquired = await self._redis.set(
                self._key,
                self._token,
                nx=True,
                ex=_LOCK_TTL_SECONDS,
            )
            if acquired:
                return self
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RETRY_MAX_SECONDS)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.watch(self._key)
            current = await self._redis.get(self._key)
            if current != self._token:
                await pipe.unwatch()  # type: ignore[no-untyped-call]
                return
            pipe.multi()  # type: ignore[no-untyped-call]
            pipe.delete(self._key)
            await pipe.execute()


def make_local_budget_lock_factory() -> BudgetLockFactory:
    def _factory(run_id: UUID | None) -> BudgetLockProtocol:
        return LocalBudgetLock(run_id)

    return _factory


def make_redis_budget_lock_factory(redis: Redis) -> BudgetLockFactory:
    def _factory(run_id: UUID | None) -> BudgetLockProtocol:
        return RedisBudgetLock(redis, run_id)

    return _factory


def reset_local_budget_lock_registry() -> None:
    """Test helper. Clears the in-process registry so each test starts clean."""
    LocalBudgetLock._registry.clear()


__all__ = [
    "BudgetLockFactory",
    "BudgetLockProtocol",
    "LocalBudgetLock",
    "RedisBudgetLock",
    "make_local_budget_lock_factory",
    "make_redis_budget_lock_factory",
    "reset_local_budget_lock_registry",
]
