from collections.abc import Iterator
from decimal import Decimal

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def _set_tiingo_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_tiingo_latest_parses_list() -> None:
    from app.services.source_clients.tiingo import fetch_tiingo_latest

    respx.get("https://api.tiingo.com/iex/AAPL").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "ticker": "AAPL",
                    "last": "190.5",
                    "timestamp": "2024-01-02T20:00:00+00:00",
                    "askPrice": "190.6",
                    "bidPrice": "190.4",
                    "volume": 1000000,
                }
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        quotes, content_hash = await fetch_tiingo_latest(client=client, ticker="AAPL")

    assert len(quotes) == 1
    assert quotes[0].ticker == "AAPL"
    assert quotes[0].last == Decimal("190.5")
    assert quotes[0].volume == 1000000
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_tiingo_latest_sends_token_header() -> None:
    from app.services.source_clients.tiingo import fetch_tiingo_latest

    route = respx.get("https://api.tiingo.com/iex/MSFT").mock(
        return_value=httpx.Response(200, json=[])
    )

    async with httpx.AsyncClient() as client:
        await fetch_tiingo_latest(client=client, ticker="MSFT")

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Token tiingo-test-key"


async def test_fetch_tiingo_latest_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.tiingo import fetch_tiingo_latest

    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_tiingo_latest(client=client, ticker="AAPL")

    assert exc_info.value.setting_name == "tiingo_api_key"


@respx.mock
async def test_fetch_tiingo_latest_400_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.tiingo import fetch_tiingo_latest

    route = respx.get("https://api.tiingo.com/iex/AAPL").mock(
        return_value=httpx.Response(400)
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_tiingo_latest(client=client, ticker="AAPL")

    assert route.call_count == 1


@respx.mock
async def test_fetch_tiingo_daily_prices_parses_history() -> None:
    from datetime import date

    from app.services.source_clients.tiingo import fetch_tiingo_daily_prices

    respx.get("https://api.tiingo.com/tiingo/daily/AAPL/prices").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "date": "2024-01-02T00:00:00.000Z",
                    "open": 187.15,
                    "high": 188.44,
                    "low": 183.89,
                    "close": 185.64,
                    "volume": 82488700,
                    "adjClose": 185.64,
                },
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        rows, content_hash = await fetch_tiingo_daily_prices(
            client=client,
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )

    assert len(rows) == 1
    assert rows[0].close == Decimal("185.64")
    assert len(content_hash) == 64


def test_tiingo_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import tiingo
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(tiingo._RATE_LIMITER, RateLimiter)
