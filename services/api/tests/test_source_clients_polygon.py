from collections.abc import Iterator

import httpx
import pytest
import respx

_POLYGON_TICKERS_URL = "https://api.polygon.io/v3/reference/tickers"
_POLYGON_AGGREGATES_URL = (
    "https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/2024-01-01/2024-01-05"
)


@pytest.fixture(autouse=True)
def _set_polygon_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("POLYGON_API_KEY", "polygon-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_polygon_tickers_parses_results() -> None:
    from app.services.source_clients.polygon import fetch_polygon_tickers

    respx.get(_POLYGON_TICKERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "market": "stocks",
                        "primary_exchange": "XNAS",
                        "active": True,
                    },
                ],
                "status": "OK",
                "count": 1,
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_polygon_tickers(client=client)

    assert len(result.results) == 1
    assert result.results[0].ticker == "AAPL"
    assert result.results[0].active is True
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_polygon_tickers_sends_api_key_and_optional_market() -> None:
    from app.services.source_clients.polygon import fetch_polygon_tickers

    route = respx.get(_POLYGON_TICKERS_URL).mock(
        return_value=httpx.Response(
            200, json={"results": [], "status": "OK", "count": 0}
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_polygon_tickers(client=client, market="stocks", limit=50)

    sent = route.calls.last.request
    assert sent.url.params["apiKey"] == "polygon-test-key"
    assert sent.url.params["market"] == "stocks"
    assert sent.url.params["limit"] == "50"


async def test_fetch_polygon_tickers_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.polygon import fetch_polygon_tickers

    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_polygon_tickers(client=client)

    assert exc_info.value.setting_name == "polygon_api_key"


@respx.mock
async def test_fetch_polygon_tickers_403_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.polygon import fetch_polygon_tickers

    route = respx.get(_POLYGON_TICKERS_URL).mock(return_value=httpx.Response(403))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_polygon_tickers(client=client)

    assert exc_info.value.status_code == 403
    assert route.call_count == 1


@respx.mock
async def test_fetch_polygon_aggregates_parses_bars() -> None:
    from datetime import date

    from app.services.source_clients.polygon import fetch_polygon_aggregates

    respx.get(_POLYGON_AGGREGATES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "ticker": "AAPL",
                "queryCount": 2,
                "resultsCount": 2,
                "adjusted": True,
                "results": [
                    {"v": 1000.0, "o": 100.0, "c": 101.0, "h": 102.0, "l": 99.0, "t": 1704067200000},
                    {"v": 1500.0, "o": 101.0, "c": 103.0, "h": 104.0, "l": 100.0, "t": 1704153600000},
                ],
                "status": "OK",
                "request_id": "req-1",
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_polygon_aggregates(
            client=client,
            ticker="AAPL",
            multiplier=1,
            timespan="day",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 5),
        )

    assert result.ticker == "AAPL"
    assert len(result.results) == 2
    assert result.results[0].open == 100.0
    assert result.results[0].close == 101.0
    assert len(content_hash) == 64


def test_polygon_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import polygon
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(polygon._RATE_LIMITER, RateLimiter)
