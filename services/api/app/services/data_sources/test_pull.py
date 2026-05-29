"""Dry-run orchestrator for /api/data-sources/{key}/test-pull.

Reads from the in-code registry, dispatches to the matching fetcher, wraps
the result in `DataSourceTestPullResponse`-shaped payloads, and caches by
(source_key, ticker, lookback_days) for 60s.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.schemas.data_sources import (
    DataSourceTestPullResponse,
    TestPullError,
)
from app.services.data_sources import fetchers as data_source_fetchers
from app.services.data_sources.fetchers import TestPullPayload
from app.services.data_sources.registry import (
    DataSourceEntry,
    get_entry,
)

CACHE_TTL_SECONDS: int = 60
CACHE_MAX_ENTRIES: int = 256

_LOOKBACK_AWARE_TICKER_FETCHERS: frozenset[str] = frozenset(
    {
        "finnhub_insider_transactions",
        "finnhub_news",
        "polygon_aggregates",
    }
)

_TICKER_FETCHER_ATTR_NAMES: dict[str, str] = {
    "finnhub_insider_transactions": "fetch_finnhub_insider_transactions",
    "finnhub_news": "fetch_finnhub_news",
    "finnhub_peers": "fetch_finnhub_peers",
    "finnhub_price_target": "fetch_finnhub_price_target",
    "finnhub_profile": "fetch_finnhub_profile",
    "finnhub_recommendation": "fetch_finnhub_recommendation",
    "polygon_aggregates": "fetch_polygon_aggregates",
    "sec_filings": "fetch_sec_filings",
    "tiingo_news_items": "fetch_tiingo_news_items",
    "gdelt": "fetch_gdelt",
}

_MACRO_FETCHER_ATTR_NAMES: dict[str, str] = {
    "fred_observations": "fetch_fred_observations",
    "fed_press": "fetch_fed_press",
    "cme_fedwatch": "fetch_cme_fedwatch",
    "kalshi_markets": "fetch_kalshi_markets",
    "polymarket_events": "fetch_polymarket_events",
    "polymarket_price_history": "fetch_polymarket_price_history",
    "congress_bills": "fetch_congress_bills",
}


class UnknownSourceKeyError(Exception):
    pass


class MissingTickerError(Exception):
    pass


@dataclass(frozen=True)
class TestPullCacheKey:
    source_key: str
    ticker: str | None
    lookback_days: int | None

    def cache_str(self) -> str:
        ticker_part = self.ticker or "-"
        lookback_part = str(self.lookback_days) if self.lookback_days is not None else "-"
        return f"data_sources:test_pull:{self.source_key}:{ticker_part}:{lookback_part}"


class TestPullCache(Protocol):
    async def get(self, key: TestPullCacheKey) -> DataSourceTestPullResponse | None: ...
    async def set(self, key: TestPullCacheKey, response: DataSourceTestPullResponse) -> None: ...


class InMemoryTestPullCache:
    def __init__(
        self,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        max_entries: int = CACHE_MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: OrderedDict[str, tuple[float, DataSourceTestPullResponse]] = OrderedDict()

    async def get(
        self, key: TestPullCacheKey
    ) -> DataSourceTestPullResponse | None:
        cache_key = key.cache_str()
        entry = self._store.get(cache_key)
        if entry is None:
            return None
        expires_at, response = entry
        if expires_at < time.monotonic():
            del self._store[cache_key]
            return None
        self._store.move_to_end(cache_key)
        return response

    async def set(
        self, key: TestPullCacheKey, response: DataSourceTestPullResponse
    ) -> None:
        cache_key = key.cache_str()
        expires_at = time.monotonic() + self._ttl
        self._store[cache_key] = (expires_at, response)
        self._store.move_to_end(cache_key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)


def _resolve_lookback(entry: DataSourceEntry, requested: int | None) -> int | None:
    if requested is not None:
        return requested
    return entry.default_lookback_days


async def _dispatch(
    entry: DataSourceEntry,
    ticker: str | None,
    lookback_days: int | None,
    client: httpx.AsyncClient,
) -> TestPullPayload:
    if entry.scope == "ticker":
        if ticker is None:
            raise MissingTickerError(entry.key)
        attr_name = _TICKER_FETCHER_ATTR_NAMES[entry.key]
        fetcher = getattr(data_source_fetchers, attr_name)
        kwargs: dict[str, object] = {"client": client, "ticker": ticker}
        if entry.key in _LOOKBACK_AWARE_TICKER_FETCHERS and lookback_days is not None:
            kwargs["lookback_days"] = lookback_days
        return await fetcher(**kwargs)
    attr_name = _MACRO_FETCHER_ATTR_NAMES[entry.key]
    fetcher = getattr(data_source_fetchers, attr_name)
    return await fetcher(client=client)


class TestPullOrchestrator:
    def __init__(self, cache: TestPullCache) -> None:
        self._cache = cache

    async def run(
        self,
        source_key: str,
        ticker: str | None,
        lookback_days: int | None,
        http_client: httpx.AsyncClient,
    ) -> DataSourceTestPullResponse:
        entry = get_entry(source_key)
        if entry is None:
            raise UnknownSourceKeyError(source_key)
        effective_lookback = _resolve_lookback(entry, lookback_days)
        cache_key = TestPullCacheKey(
            source_key=source_key,
            ticker=ticker,
            lookback_days=effective_lookback,
        )
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        started_at = time.perf_counter()
        try:
            payload = await _dispatch(entry, ticker, effective_lookback, http_client)
        except (MissingTickerError, UnknownSourceKeyError):
            raise
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            response = DataSourceTestPullResponse(
                source_key=source_key,
                status="error",
                latency_ms=latency_ms,
                count=0,
                as_of=None,
                preview=[],
                raw=None,
                error=TestPullError(code=type(exc).__name__, detail=str(exc)),
            )
            return response

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        response = DataSourceTestPullResponse(
            source_key=source_key,
            status="ok",
            latency_ms=latency_ms,
            count=len(payload.rows),
            as_of=payload.as_of,
            preview=payload.rows,
            raw=payload.raw,
            error=None,
        )
        await self._cache.set(cache_key, response)
        return response


__all__ = [
    "CACHE_MAX_ENTRIES",
    "CACHE_TTL_SECONDS",
    "InMemoryTestPullCache",
    "MissingTickerError",
    "TestPullCache",
    "TestPullCacheKey",
    "TestPullOrchestrator",
    "UnknownSourceKeyError",
]
