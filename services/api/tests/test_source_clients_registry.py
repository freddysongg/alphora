"""Tests for the source-client lazy rate-limiter registry."""
import fakeredis.aioredis
import pytest

from app.services.source_clients._rate_limit import (
    LocalTokenBucket,
    RedisTokenBucket,
)
from app.services.source_clients._registry import (
    configure_redis,
    get_rate_limiter,
    get_request_cache,
    install_request_cache,
    reset_registry,
)
from app.services.source_clients._request_cache import RequestCache


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_registry()
    yield
    reset_registry()


def test_get_rate_limiter_returns_local_bucket_without_redis() -> None:
    limiter = get_rate_limiter(name="t", rate_per_second=1.0, burst=2)
    assert isinstance(limiter, LocalTokenBucket)


def test_get_rate_limiter_caches_by_name() -> None:
    first = get_rate_limiter(name="cached", rate_per_second=1.0, burst=2)
    second = get_rate_limiter(name="cached", rate_per_second=99.0, burst=99)
    assert first is second


def test_get_rate_limiter_distinct_names_distinct_instances() -> None:
    a = get_rate_limiter(name="a", rate_per_second=1.0, burst=2)
    b = get_rate_limiter(name="b", rate_per_second=1.0, burst=2)
    assert a is not b


def test_configure_redis_swaps_to_redis_bucket_on_next_get() -> None:
    local = get_rate_limiter(name="swap", rate_per_second=1.0, burst=2)
    assert isinstance(local, LocalTokenBucket)
    configure_redis(fakeredis.aioredis.FakeRedis())
    upgraded = get_rate_limiter(name="swap", rate_per_second=1.0, burst=2)
    assert isinstance(upgraded, RedisTokenBucket)
    assert upgraded is not local


def test_configure_redis_to_none_returns_to_local() -> None:
    configure_redis(fakeredis.aioredis.FakeRedis())
    redis_backed = get_rate_limiter(name="back", rate_per_second=1.0, burst=2)
    assert isinstance(redis_backed, RedisTokenBucket)
    configure_redis(None)
    local_again = get_rate_limiter(name="back", rate_per_second=1.0, burst=2)
    assert isinstance(local_again, LocalTokenBucket)


def test_install_request_cache_round_trip() -> None:
    assert get_request_cache() is None
    cache = RequestCache(ttl_seconds=60.0)
    install_request_cache(cache)
    assert get_request_cache() is cache
    install_request_cache(None)
    assert get_request_cache() is None


def test_reset_registry_clears_redis_and_cache() -> None:
    configure_redis(fakeredis.aioredis.FakeRedis())
    install_request_cache(RequestCache(ttl_seconds=60.0))
    redis_backed = get_rate_limiter(name="reset-me", rate_per_second=1.0, burst=2)
    assert isinstance(redis_backed, RedisTokenBucket)
    reset_registry()
    assert get_request_cache() is None
    local = get_rate_limiter(name="reset-me", rate_per_second=1.0, burst=2)
    assert isinstance(local, LocalTokenBucket)
