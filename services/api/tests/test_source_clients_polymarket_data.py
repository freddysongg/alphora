import httpx
import pytest
import respx

_HISTORY_URL = "https://data-api.polymarket.com/prices-history"


def _sample_payload() -> dict[str, object]:
    return {
        "market": "us-presidential-election-2028",
        "interval": "1d",
        "history": [
            {"t": 1714521600, "p": 0.42, "v": 8124032.55},
            {"t": 1714608000, "p": 0.44, "v": 6532112.10},
            {"t": 1714694400, "p": 0.47, "v": 12340921.78},
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_polymarket_price_history_parses_points() -> None:
    from app.services.source_clients.polymarket_data import (
        fetch_polymarket_price_history,
    )

    respx.get(_HISTORY_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_polymarket_price_history(
            client=client, market="us-presidential-election-2028"
        )

    assert result.market == "us-presidential-election-2028"
    assert result.interval == "1d"
    assert len(result.history) == 3
    assert result.history[0].timestamp_s == 1714521600
    assert result.history[0].probability == pytest.approx(0.42)
    assert result.history[0].volume_usd == pytest.approx(8124032.55)
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_polymarket_price_history_accepts_bare_array_shape() -> None:
    from app.services.source_clients.polymarket_data import (
        fetch_polymarket_price_history,
    )

    respx.get(_HISTORY_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"t": 1714521600, "p": 0.42, "v": 100.0},
                {"t": 1714608000, "p": 0.43},
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_polymarket_price_history(
            client=client, market="m", interval="1h"
        )

    assert result.market == "m"
    assert result.interval == "1h"
    assert len(result.history) == 2
    assert result.history[1].volume_usd is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_polymarket_price_history_forwards_filters() -> None:
    from app.services.source_clients.polymarket_data import (
        fetch_polymarket_price_history,
    )

    route = respx.get(_HISTORY_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        await fetch_polymarket_price_history(
            client=client,
            market="m",
            interval="1w",
            start_ts=1714521600,
            end_ts=1715126400,
        )

    sent = route.calls.last.request
    assert sent.url.params["market"] == "m"
    assert sent.url.params["interval"] == "1w"
    assert sent.url.params["startTs"] == "1714521600"
    assert sent.url.params["endTs"] == "1715126400"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_polymarket_price_history_500_retries() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.polymarket_data import (
        fetch_polymarket_price_history,
    )

    route = respx.get(_HISTORY_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_polymarket_price_history(client=client, market="m")

    assert route.call_count == 4


def test_polymarket_data_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import polymarket_data
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = polymarket_data._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert polymarket_data._rate_limiter() is limiter


def test_polymarket_data_limiter_distinct_from_gamma() -> None:
    """data-api and gamma-api share `polymarket` infra but use distinct registry
    keys so a burst on one does not throttle the other."""
    from app.services.source_clients import polymarket, polymarket_data
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    gamma = polymarket._rate_limiter()
    data = polymarket_data._rate_limiter()
    assert gamma is not data
