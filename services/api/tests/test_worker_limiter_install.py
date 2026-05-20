"""Verify the worker installs a Redis client + request cache into the registry."""
from unittest.mock import MagicMock

import pytest

import app.workers.tasks as tasks_module
from app.services.source_clients import _registry
from app.services.source_clients._rate_limit import RedisTokenBucket
from app.services.source_clients._registry import (
    get_rate_limiter,
    get_request_cache,
    reset_registry,
)
from app.services.source_clients._request_cache import RequestCache


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset both the registry and the worker's one-shot flag."""
    reset_registry()
    tasks_module._LIMITER_CONFIGURED = False
    tasks_module._CACHED_WORKER_REDIS = None
    yield
    reset_registry()
    tasks_module._LIMITER_CONFIGURED = False
    tasks_module._CACHED_WORKER_REDIS = None


def test_install_async_redis_limiter_binds_redis_client_to_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call should install a Redis client + request cache."""
    fake_redis = MagicMock()
    monkeypatch.setattr(tasks_module, "_get_worker_redis", lambda: fake_redis)
    tasks_module._install_async_redis_limiter()

    limiter = get_rate_limiter(
        name="worker-install", rate_per_second=1.0, burst=2
    )
    assert isinstance(limiter, RedisTokenBucket)
    cache = get_request_cache()
    assert isinstance(cache, RequestCache)
    assert cache.ttl_seconds == pytest.approx(300.0)


def test_install_async_redis_limiter_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second invocation must not thrash the limiter cache."""
    fake_redis = MagicMock()
    monkeypatch.setattr(tasks_module, "_get_worker_redis", lambda: fake_redis)
    tasks_module._install_async_redis_limiter()
    limiter_first = get_rate_limiter(
        name="idem", rate_per_second=1.0, burst=2
    )
    tasks_module._install_async_redis_limiter()
    limiter_second = get_rate_limiter(
        name="idem", rate_per_second=1.0, burst=2
    )
    assert limiter_first is limiter_second


def test_install_async_redis_limiter_caches_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker should hold a single async Redis client across the process."""
    counter = {"count": 0}
    fake_redis = MagicMock()

    def fake_from_url(*_args: object, **_kwargs: object) -> object:
        counter["count"] += 1
        return fake_redis

    from redis.asyncio import Redis as AsyncRedis

    monkeypatch.setattr(AsyncRedis, "from_url", fake_from_url)
    first = tasks_module._get_worker_redis()
    second = tasks_module._get_worker_redis()
    assert first is second
    assert counter["count"] == 1


def test_registry_reset_clears_install_state() -> None:
    """`reset_registry` clears the cache/client without affecting worker flag."""
    _registry.configure_redis(MagicMock())
    _registry.install_request_cache(RequestCache(ttl_seconds=30.0))
    reset_registry()
    assert get_request_cache() is None
