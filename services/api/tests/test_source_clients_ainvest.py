from collections.abc import Iterator

import httpx
import pytest
import respx

_AINVEST_URL = "https://openapi.ainvest.com/open/ownership/congress"


@pytest.fixture(autouse=True)
def _set_ainvest_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("AINVEST_API_KEY", "ainvest-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_ainvest_congress_transactions_parses_documented_envelope() -> None:
    from datetime import date

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
                            "name": "Nancy Pelosi",
                            "party": "D",
                            "state": "CA",
                            "trade_date": "2024-01-15",
                            "filing_date": "2024-02-10",
                            "reporting_gap": "26 days",
                            "trade_type": "buy",
                            "size": "$1,000,001 - $5,000,000",
                        }
                    ],
                },
                "status_code": 0,
                "status_msg": "ok",
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_ainvest_congress_transactions(
            client=client, ticker="NVDA"
        )

    assert result.status_code == 0
    assert result.status_msg == "ok"
    assert len(result.data.data) == 1
    row = result.data.data[0]
    assert row.name == "Nancy Pelosi"
    assert row.party == "D"
    assert row.state == "CA"
    assert row.trade_date == date(2024, 1, 15)
    assert row.filing_date == date(2024, 2, 10)
    assert row.reporting_gap == "26 days"
    assert row.trade_type == "buy"
    assert row.size == "$1,000,001 - $5,000,000"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_ainvest_congress_transactions_uses_bearer_auth_and_ticker_param() -> None:
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    route = respx.get(_AINVEST_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"data": []}, "status_code": 0, "status_msg": "ok"},
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_ainvest_congress_transactions(client=client, ticker="AAPL")

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer ainvest-test-key"
    assert "X-API-KEY" not in sent.headers
    assert sent.url.params["ticker"] == "AAPL"
    assert "page" not in sent.url.params
    assert "size" not in sent.url.params


@respx.mock
async def test_fetch_ainvest_congress_transactions_passes_pagination_params() -> None:
    from app.services.source_clients.ainvest import (
        fetch_ainvest_congress_transactions,
    )

    route = respx.get(_AINVEST_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"data": []}, "status_code": 0, "status_msg": "ok"},
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_ainvest_congress_transactions(
            client=client,
            ticker="MSFT",
            page=2,
            size=50,
        )

    sent = route.calls.last.request
    assert sent.url.params["page"] == "2"
    assert sent.url.params["size"] == "50"


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
