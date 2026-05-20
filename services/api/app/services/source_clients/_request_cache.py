"""TTL-based in-process cache for source-client GET responses.

Same-context worker calls within the cache TTL (5 minutes by default) share
results so that, e.g., sector fan-outs spawning parallel requests to the same
SEC EDGAR submission URL only fetch once. The cache is process-local: the
API process never installs one; the worker process installs a single shared
`RequestCache` at boot.

Cache key is the canonical (method, url, sorted params, sorted JSON body).
Auth headers are intentionally excluded — the worker process uses one set of
credentials over its lifetime, and the cache key already isolates by URL +
query.

Only successful GET responses (2xx/3xx) are cached. POST responses are not
cached because most POSTs in the codebase are mutating (the OpenFIGI mapping
is the rare exception and is opted in explicitly by passing the body).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class _CacheEntry:
    body_bytes: bytes
    headers: dict[str, str]
    status_code: int
    content_hash: str
    url: str
    cached_at: float


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    evictions: int

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total


class RequestCache:
    """Async-safe TTL cache keyed by the canonical request signature.

    Designed to be installed once per worker process via
    `app.services.source_clients._registry.install_request_cache`.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0.0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._store: dict[str, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._hits, misses=self._misses, evictions=self._evictions
        )

    @staticmethod
    def cache_key(
        *,
        method: str,
        url: str,
        params: Mapping[str, object] | None,
        json_body: Mapping[str, object] | None,
    ) -> str:
        payload = {
            "method": method,
            "url": url,
            "params": _canonicalize(params),
            "json_body": _canonicalize(json_body),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> _CacheEntry | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            age = self._clock() - entry.cached_at
            if age > self._ttl_seconds:
                self._store.pop(key, None)
                self._evictions += 1
                self._misses += 1
                return None
            self._hits += 1
            return entry

    async def set(
        self,
        *,
        key: str,
        body_bytes: bytes,
        headers: Mapping[str, str],
        status_code: int,
        content_hash: str,
        url: str,
    ) -> None:
        async with self._lock:
            self._store[key] = _CacheEntry(
                body_bytes=body_bytes,
                headers=dict(headers),
                status_code=status_code,
                content_hash=content_hash,
                url=url,
                cached_at=self._clock(),
            )


def _canonicalize(value: Mapping[str, object] | None) -> object | None:
    if value is None:
        return None
    return {k: str(v) for k, v in sorted(value.items())}


__all__ = ["CacheStats", "RequestCache"]
