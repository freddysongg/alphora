import httpx
import pytest
import respx

from app.config import get_settings
from app.services.source_clients._http import SourceClientConfigError

_FAKE_RESPONSE = [
    {
        "id": 100,
        "title": "Fed holds rates steady",
        "description": "FOMC decision today",
        "url": "https://example.com/a",
        "publishedDate": "2026-05-18T14:00:00Z",
        "source": "Reuters",
        "tickers": ["spy", "tlt"],
        "tags": ["fed", "rates"],
    }
]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tiingo_news_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    get_settings.cache_clear()

    route = respx.get("https://api.tiingo.com/tiingo/news").mock(
        return_value=httpx.Response(200, json=_FAKE_RESPONSE)
    )
    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_tiingo_news(client=client, limit=10)

    assert route.called
    assert len(items) == 1
    assert items[0].id == 100
    assert items[0].source == "Reuters"
    assert items[0].tickers == ["spy", "tlt"]
    assert content_hash and len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_tiingo_news_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    get_settings.cache_clear()
    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError):
            await fetch_tiingo_news(client=client)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tiingo_news_passes_tickers_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    get_settings.cache_clear()

    route = respx.get(
        "https://api.tiingo.com/tiingo/news",
        params={"tickers": "aapl,msft", "limit": 5},
    ).mock(return_value=httpx.Response(200, json=[]))

    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_tiingo_news(
            client=client, tickers=["aapl", "msft"], limit=5
        )

    assert route.called
    assert items == []
