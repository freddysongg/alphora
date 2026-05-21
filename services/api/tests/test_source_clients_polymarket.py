import httpx
import pytest
import respx

_EVENTS_URL = "https://gamma-api.polymarket.com/events"
_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


@respx.mock
async def test_fetch_polymarket_events_parses_list() -> None:
    from app.services.source_clients.polymarket import fetch_polymarket_events

    respx.get(_EVENTS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "12345",
                    "slug": "us-election-2024",
                    "title": "2024 US Presidential Election",
                    "active": True,
                    "closed": False,
                    "category": "Politics",
                }
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        events, content_hash = await fetch_polymarket_events(client=client)

    assert len(events) == 1
    assert events[0].slug == "us-election-2024"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_polymarket_events_passes_query_params() -> None:
    from app.services.source_clients.polymarket import fetch_polymarket_events

    route = respx.get(_EVENTS_URL).mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        await fetch_polymarket_events(client=client, limit=50, active=True)

    sent = route.calls.last.request
    assert sent.url.params["limit"] == "50"
    assert sent.url.params["active"] == "true"


@respx.mock
async def test_fetch_polymarket_events_500_retries_until_failure() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.polymarket import fetch_polymarket_events

    route = respx.get(_EVENTS_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_polymarket_events(client=client)

    assert route.call_count == 4  # 1 initial + 3 retries


@respx.mock
async def test_fetch_polymarket_markets_decodes_json_encoded_string_arrays() -> None:
    from app.services.source_clients.polymarket import fetch_polymarket_markets

    respx.get(_MARKETS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "abc-123",
                    "question": "Will X happen?",
                    "slug": "will-x-happen",
                    "outcomes": "[\"Yes\", \"No\"]",
                    "outcomePrices": "[\"0.62\", \"0.38\"]",
                    "volume": "12345.67",
                    "liquidity": "9999.99",
                    "active": True,
                    "closed": False,
                }
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        markets, content_hash = await fetch_polymarket_markets(client=client)

    assert len(markets) == 1
    assert markets[0].question == "Will X happen?"
    assert markets[0].outcomes == ["Yes", "No"]
    assert markets[0].outcome_prices == ["0.62", "0.38"]
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_polymarket_markets_accepts_native_array_shape() -> None:
    from app.services.source_clients.polymarket import fetch_polymarket_markets

    respx.get(_MARKETS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "def-456",
                    "question": "Will Y happen?",
                    "slug": "will-y-happen",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.5", "0.5"],
                    "active": True,
                    "closed": False,
                }
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        markets, _ = await fetch_polymarket_markets(client=client)

    assert markets[0].outcomes == ["Yes", "No"]
    assert markets[0].outcome_prices == ["0.5", "0.5"]


@respx.mock
async def test_fetch_polymarket_markets_omits_outcomes_when_missing() -> None:
    from app.services.source_clients.polymarket import fetch_polymarket_markets

    respx.get(_MARKETS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "ghi-789",
                    "question": "Will Z happen?",
                    "slug": "will-z-happen",
                }
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        markets, _ = await fetch_polymarket_markets(client=client)

    assert markets[0].outcomes == []
    assert markets[0].outcome_prices == []


@respx.mock
async def test_fetch_polymarket_markets_400_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.polymarket import fetch_polymarket_markets

    route = respx.get(_MARKETS_URL).mock(return_value=httpx.Response(400))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_polymarket_markets(client=client)

    assert route.call_count == 1


def test_polymarket_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import polymarket
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = polymarket._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert polymarket._rate_limiter() is limiter
