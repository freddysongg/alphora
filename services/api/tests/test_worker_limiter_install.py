"""Verify the worker installs a Redis client + request cache into the registry
inside the per-job asyncio.run, so the connection pool is bound to the live
event loop (not the worker process lifetime)."""
from unittest.mock import AsyncMock, MagicMock

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
    reset_registry()
    yield
    reset_registry()


@pytest.mark.asyncio
async def test_run_with_source_client_runtime_binds_redis_client_during_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """During `_run_with_source_client_runtime`, the registry must hold a
    Redis-backed limiter and the request cache."""
    seen: dict[str, object] = {}

    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    async def _noop_bootstrap() -> None:
        return None

    monkeypatch.setattr(
        tasks_module, "_bootstrap_data_sources_for_run", _noop_bootstrap
    )

    async def fake_dispatch(_: object) -> None:
        seen["limiter"] = get_rate_limiter(
            name="dispatch-probe", rate_per_second=1.0, burst=2
        )
        seen["request_cache"] = get_request_cache()

    monkeypatch.setattr(tasks_module, "_dispatch", fake_dispatch)

    from uuid import uuid4
    await tasks_module._run_with_source_client_runtime(uuid4())

    assert isinstance(seen["limiter"], RedisTokenBucket)
    assert isinstance(seen["request_cache"], RequestCache)
    assert seen["request_cache"].ttl_seconds == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_run_with_source_client_runtime_tears_down_state_after_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After dispatch returns, the registry must be cleared and the Redis
    client must be closed inside the same event loop that built it."""
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    async def _noop_bootstrap() -> None:
        return None

    monkeypatch.setattr(
        tasks_module, "_bootstrap_data_sources_for_run", _noop_bootstrap
    )

    async def noop_dispatch(_: object) -> None:
        return None

    monkeypatch.setattr(tasks_module, "_dispatch", noop_dispatch)

    from uuid import uuid4
    await tasks_module._run_with_source_client_runtime(uuid4())

    assert get_request_cache() is None
    fake_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_with_source_client_runtime_tears_down_on_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when dispatch raises, the Redis client must still be closed and
    the registry cleared — otherwise a flaky run leaks the connection pool
    across jobs."""
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    async def _noop_bootstrap() -> None:
        return None

    monkeypatch.setattr(
        tasks_module, "_bootstrap_data_sources_for_run", _noop_bootstrap
    )

    async def failing_dispatch(_: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks_module, "_dispatch", failing_dispatch)

    from uuid import uuid4
    with pytest.raises(RuntimeError, match="boom"):
        await tasks_module._run_with_source_client_runtime(uuid4())

    assert get_request_cache() is None
    fake_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_async_redis_falls_back_to_close_when_aclose_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older redis-py builds expose `close()` but not `aclose()`; the worker
    must fall back so it never leaks a pool."""

    fake_redis = MagicMock(spec=["close"])
    fake_redis.close = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    async def _noop_bootstrap() -> None:
        return None

    monkeypatch.setattr(
        tasks_module, "_bootstrap_data_sources_for_run", _noop_bootstrap
    )

    async def noop_dispatch(_: object) -> None:
        return None

    monkeypatch.setattr(tasks_module, "_dispatch", noop_dispatch)

    from uuid import uuid4
    await tasks_module._run_with_source_client_runtime(uuid4())

    fake_redis.close.assert_awaited_once()


def test_registry_reset_clears_install_state() -> None:
    """`reset_registry` clears the cache/client; the worker module no longer
    holds module-level Redis state, so there's nothing else to clear."""
    _registry.configure_redis(MagicMock())
    _registry.install_request_cache(RequestCache(ttl_seconds=30.0))
    reset_registry()
    assert get_request_cache() is None
