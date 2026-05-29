from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.data_sources.fetchers import TestPullPayload


@pytest.mark.asyncio
async def test_test_pull_returns_preview(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "x")
    from app.config import get_settings

    get_settings.cache_clear()
    payload = TestPullPayload(rows=[{"headline": "h"}], raw="[]", as_of=None)
    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news",
        AsyncMock(return_value=payload),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL", "lookback_days": 30},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["preview"] == [{"headline": "h"}]
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_test_pull_unknown_source_404(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/no_such/test-pull", json={"ticker": "AAPL"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_pull_missing_ticker_422(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull", json={}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_pull_missing_api_key_503(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL"},
        )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_test_pull_disabled_source_409(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.patch(
            "/api/data-sources/finnhub_news", json={"enabled": False}
        )
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL"},
        )
    assert response.status_code == 409
