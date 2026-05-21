"""Tests for `RequestCache` — TTL semantics, key canonicalization, stats."""
import pytest

from app.services.source_clients._request_cache import CacheStats, RequestCache


def test_cache_key_is_stable_for_canonical_params() -> None:
    a = RequestCache.cache_key(
        method="GET",
        url="https://x/y",
        params={"b": 1, "a": "x"},
        json_body=None,
    )
    b = RequestCache.cache_key(
        method="GET",
        url="https://x/y",
        params={"a": "x", "b": 1},
        json_body=None,
    )
    assert a == b


def test_cache_key_distinct_for_different_urls() -> None:
    a = RequestCache.cache_key(method="GET", url="u1", params=None, json_body=None)
    b = RequestCache.cache_key(method="GET", url="u2", params=None, json_body=None)
    assert a != b


def test_cache_key_distinct_for_different_methods() -> None:
    a = RequestCache.cache_key(method="GET", url="u", params=None, json_body=None)
    b = RequestCache.cache_key(method="POST", url="u", params=None, json_body=None)
    assert a != b


def test_ttl_zero_raises() -> None:
    with pytest.raises(ValueError):
        RequestCache(ttl_seconds=0.0)


def test_ttl_negative_raises() -> None:
    with pytest.raises(ValueError):
        RequestCache(ttl_seconds=-1.0)


@pytest.mark.asyncio
async def test_miss_increments_misses_stat() -> None:
    cache = RequestCache(ttl_seconds=60.0)
    assert await cache.get("missing") is None
    stats = cache.stats()
    assert stats.misses == 1
    assert stats.hits == 0


@pytest.mark.asyncio
async def test_set_then_get_returns_cached_entry() -> None:
    cache = RequestCache(ttl_seconds=60.0)
    await cache.set(
        key="k",
        body_bytes=b"payload",
        headers={"Content-Type": "application/json"},
        status_code=200,
        content_hash="abc",
        url="https://x/y",
    )
    entry = await cache.get("k")
    assert entry is not None
    assert entry.body_bytes == b"payload"
    assert entry.status_code == 200
    assert entry.content_hash == "abc"
    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 0


@pytest.mark.asyncio
async def test_expired_entry_returns_none_and_evicts() -> None:
    fake_now = [1000.0]

    def fake_clock() -> float:
        return fake_now[0]

    cache = RequestCache(ttl_seconds=10.0, clock=fake_clock)
    await cache.set(
        key="k",
        body_bytes=b"",
        headers={},
        status_code=200,
        content_hash="",
        url="",
    )
    fake_now[0] = 1015.0
    assert await cache.get("k") is None
    stats = cache.stats()
    assert stats.evictions == 1


def test_cache_stats_hit_rate_when_empty() -> None:
    stats = CacheStats(hits=0, misses=0, evictions=0)
    assert stats.total == 0
    assert stats.hit_rate == 0.0


def test_cache_stats_hit_rate_computation() -> None:
    stats = CacheStats(hits=3, misses=1, evictions=0)
    assert stats.total == 4
    assert stats.hit_rate == 0.75


@pytest.mark.asyncio
async def test_only_hit_within_ttl_window() -> None:
    fake_now = [100.0]

    def fake_clock() -> float:
        return fake_now[0]

    cache = RequestCache(ttl_seconds=60.0, clock=fake_clock)
    await cache.set(
        key="k",
        body_bytes=b"x",
        headers={},
        status_code=200,
        content_hash="",
        url="",
    )
    fake_now[0] = 159.0  # within window
    assert await cache.get("k") is not None
    fake_now[0] = 161.0  # past window
    assert await cache.get("k") is None
