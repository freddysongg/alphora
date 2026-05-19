import httpx
import pytest
import respx

_KALSHI_MARKETS_URL = "https://external-api.kalshi.com/trade-api/v2/markets"
_KALSHI_MARKET_DETAIL_URL = (
    "https://external-api.kalshi.com/trade-api/v2/markets/INXD-23DEC29-T4500"
)


@respx.mock
async def test_fetch_kalshi_markets_parses_payload() -> None:
    from app.services.source_clients.kalshi import fetch_kalshi_markets

    respx.get(_KALSHI_MARKETS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "INXD-23DEC29-T4500",
                        "event_ticker": "INXD-23DEC29",
                        "title": "S&P 500 above 4500 on Dec 29",
                        "status": "open",
                        "yes_bid": 60,
                        "yes_ask": 65,
                        "open_time": "2023-12-01T14:30:00Z",
                        "close_time": "2023-12-29T21:00:00Z",
                        "volume": 1234,
                    }
                ],
                "cursor": "next-page-cursor",
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_kalshi_markets(client=client)

    assert len(result.markets) == 1
    assert result.markets[0].ticker == "INXD-23DEC29-T4500"
    assert result.cursor == "next-page-cursor"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_kalshi_markets_does_not_send_auth_headers() -> None:
    from app.services.source_clients.kalshi import fetch_kalshi_markets

    route = respx.get(_KALSHI_MARKETS_URL).mock(
        return_value=httpx.Response(200, json={"markets": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_kalshi_markets(client=client)

    sent_headers = route.calls.last.request.headers
    assert "KALSHI-ACCESS-KEY" not in sent_headers
    assert "Authorization" not in sent_headers


@respx.mock
async def test_fetch_kalshi_markets_passes_filter_params() -> None:
    from app.services.source_clients.kalshi import fetch_kalshi_markets

    route = respx.get(_KALSHI_MARKETS_URL).mock(
        return_value=httpx.Response(200, json={"markets": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_kalshi_markets(
            client=client, cursor="abc", limit=50, series_ticker="INXD"
        )

    sent = route.calls.last.request
    assert sent.url.params["cursor"] == "abc"
    assert sent.url.params["limit"] == "50"
    assert sent.url.params["series_ticker"] == "INXD"


@respx.mock
async def test_fetch_kalshi_markets_403_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.kalshi import fetch_kalshi_markets

    route = respx.get(_KALSHI_MARKETS_URL).mock(return_value=httpx.Response(403))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_kalshi_markets(client=client)

    assert route.call_count == 1


@respx.mock
async def test_fetch_kalshi_market_detail_parses_payload() -> None:
    from app.services.source_clients.kalshi import fetch_kalshi_market_detail

    respx.get(_KALSHI_MARKET_DETAIL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "market": {
                    "ticker": "INXD-23DEC29-T4500",
                    "event_ticker": "INXD-23DEC29",
                    "title": "S&P 500 above 4500 on Dec 29",
                    "status": "open",
                    "yes_bid": 60,
                    "yes_ask": 65,
                    "open_time": "2023-12-01T14:30:00Z",
                    "close_time": "2023-12-29T21:00:00Z",
                    "volume": 1234,
                }
            },
        )
    )

    async with httpx.AsyncClient() as client:
        detail, content_hash = await fetch_kalshi_market_detail(
            client=client, ticker="INXD-23DEC29-T4500"
        )

    assert detail.market.ticker == "INXD-23DEC29-T4500"
    assert len(content_hash) == 64


def test_kalshi_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import kalshi
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(kalshi._RATE_LIMITER, RateLimiter)
