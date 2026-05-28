import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_patch_persists_settings(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        update = await client.patch(
            "/api/data-sources/finnhub_news",
            json={"enabled": False, "lookback_days": 30, "notes": "rate limited"},
        )
        assert update.status_code == 200
        body = update.json()
        assert body["settings"]["enabled"] is False
        assert body["settings"]["lookback_days"] == 30
        assert body["settings"]["notes"] == "rate limited"

        again = await client.get("/api/data-sources")
        finnhub_news = next(
            entry
            for entry in again.json()["sources"]
            if entry["key"] == "finnhub_news"
        )
        assert finnhub_news["settings"]["enabled"] is False


@pytest.mark.asyncio
async def test_patch_unknown_source_returns_404(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/data-sources/no_such", json={"enabled": True}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_invalid_lookback_returns_422(initialized_schema: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/data-sources/finnhub_news", json={"lookback_days": 5}
        )
    assert response.status_code == 422
