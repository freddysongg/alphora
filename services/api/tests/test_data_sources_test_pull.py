from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.fetchers import TestPullPayload
from app.services.data_sources.test_pull import (
    InMemoryTestPullCache,
    MissingTickerError,
    TestPullCacheKey,
    TestPullOrchestrator,
    UnknownSourceKeyError,
)


@pytest.mark.asyncio
async def test_orchestrator_returns_ok_for_ticker_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = TestPullPayload(rows=[{"headline": "h"}], raw="[]", as_of=None)
    fake = AsyncMock(return_value=payload)
    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news", fake
    )
    cache = InMemoryTestPullCache()
    orchestrator = TestPullOrchestrator(cache=cache)
    async with httpx.AsyncClient() as client:
        result = await orchestrator.run(
            source_key="finnhub_news",
            ticker="AAPL",
            lookback_days=30,
            http_client=client,
        )
    assert result.status == "ok"
    assert result.count == 1
    assert result.source_key == "finnhub_news"


@pytest.mark.asyncio
async def test_orchestrator_unknown_source_raises() -> None:
    orchestrator = TestPullOrchestrator(cache=InMemoryTestPullCache())
    async with httpx.AsyncClient() as client:
        with pytest.raises(UnknownSourceKeyError):
            await orchestrator.run(
                source_key="not_a_source",
                ticker="AAPL",
                lookback_days=None,
                http_client=client,
            )


@pytest.mark.asyncio
async def test_orchestrator_missing_ticker_for_ticker_source() -> None:
    orchestrator = TestPullOrchestrator(cache=InMemoryTestPullCache())
    async with httpx.AsyncClient() as client:
        with pytest.raises(MissingTickerError):
            await orchestrator.run(
                source_key="finnhub_news",
                ticker=None,
                lookback_days=None,
                http_client=client,
            )


@pytest.mark.asyncio
async def test_orchestrator_cache_hit_avoids_second_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    payload = TestPullPayload(rows=[], raw="[]", as_of=None)

    async def fake_fetch(
        *, client: httpx.AsyncClient, ticker: str, lookback_days: int
    ) -> TestPullPayload:
        nonlocal call_count
        call_count += 1
        return payload

    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news", fake_fetch
    )
    cache = InMemoryTestPullCache()
    orchestrator = TestPullOrchestrator(cache=cache)
    async with httpx.AsyncClient() as client:
        await orchestrator.run("finnhub_news", "AAPL", 30, client)
        await orchestrator.run("finnhub_news", "AAPL", 30, client)
    assert call_count == 1


def test_cache_key_round_trip() -> None:
    key = TestPullCacheKey(source_key="finnhub_news", ticker="AAPL", lookback_days=30)
    assert key.cache_str() == "data_sources:test_pull:finnhub_news:AAPL:30"
