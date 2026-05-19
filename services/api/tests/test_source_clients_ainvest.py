from collections.abc import Iterator

import httpx
import pytest
import respx

_AINVEST_URL = "https://api.openledger.com/api/v1/ownership/congress"


@pytest.fixture(autouse=True)
def _set_ainvest_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("AINVEST_API_KEY", "ainvest-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_ainvest_congress_transactions_parses_nested_data_envelope() -> None:
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    respx.get(_AINVEST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "data": [
                        {
                            "member_name": "Nancy Pelosi",
                            "bioguide_id": "P000197",
                            "transaction_date": "2024-01-15",
                            "asset_ticker": "NVDA",
                            "asset_name": "Nvidia Corp",
                            "transaction_type": "buy",
                            "amount_range": "$1,000,001 - $5,000,000",
                        }
                    ],
                    "count": 1,
                }
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_ainvest_congress_transactions(
            client=client, ticker="NVDA"
        )

    assert result.count == 1
    assert result.transactions[0].member_name == "Nancy Pelosi"
    assert result.transactions[0].asset_ticker == "NVDA"
    assert result.transactions[0].transaction_type == "buy"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_ainvest_congress_transactions_uses_bearer_auth_and_ticker_param() -> None:
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    route = respx.get(_AINVEST_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"data": [], "count": 0}}
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_ainvest_congress_transactions(client=client, ticker="AAPL")

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer ainvest-test-key"
    assert "X-API-KEY" not in sent.headers
    assert sent.url.params["ticker"] == "AAPL"


@respx.mock
async def test_fetch_ainvest_congress_transactions_passes_date_filters() -> None:
    from datetime import date

    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    route = respx.get(_AINVEST_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"data": [], "count": 0}}
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_ainvest_congress_transactions(
            client=client,
            ticker="MSFT",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )

    sent = route.calls.last.request
    assert sent.url.params["start_date"] == "2024-01-01"
    assert sent.url.params["end_date"] == "2024-03-31"


async def test_fetch_ainvest_congress_transactions_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    monkeypatch.delenv("AINVEST_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_ainvest_congress_transactions(client=client, ticker="AAPL")

    assert exc_info.value.setting_name == "ainvest_api_key"


@respx.mock
async def test_fetch_ainvest_congress_transactions_401_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    route = respx.get(_AINVEST_URL).mock(return_value=httpx.Response(401))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_ainvest_congress_transactions(client=client, ticker="AAPL")

    assert route.call_count == 1


def test_ainvest_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import ainvest
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(ainvest._RATE_LIMITER, RateLimiter)
