import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_list_returns_all_registry_entries(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/data-sources")
    assert response.status_code == 200
    body = response.json()
    keys = [entry["key"] for entry in body["sources"]]
    assert "finnhub_news" in keys
    assert "fred_observations" in keys


@pytest.mark.asyncio
async def test_list_reflects_api_key_status(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/data-sources")
    by_key = {entry["key"]: entry for entry in response.json()["sources"]}
    assert by_key["finnhub_news"]["api_key_status"] == "configured"
    assert by_key["sec_filings"]["api_key_status"] == "n/a"
