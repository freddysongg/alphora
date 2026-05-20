import httpx
import pytest
import respx

_TEST_URL = "https://test.capitol.example/api/trades"


def _sample_payload() -> dict[str, object]:
    return {
        "page": 1,
        "page_size": 25,
        "total_count": 2,
        "trades": [
            {
                "trade_id": "ct-2026-04-001",
                "politician": {
                    "name": "Senator A. Smith",
                    "party": "Democrat",
                    "chamber": "Senate",
                    "state": "CA",
                },
                "issuer": {"ticker": "AAPL", "name": "Apple Inc."},
                "traded_at": "2026-04-01",
                "filed_at": "2026-04-25",
                "reporting_gap_days": 24,
                "transaction_type": "buy",
                "amount_range_usd": [15001, 50000],
                "owner": "self",
                "source_url": "https://www.capitoltrades.com/trades/ct-2026-04-001",
            },
            {
                "trade_id": "ct-2026-04-002",
                "politician": {
                    "name": "Rep. B. Jones",
                    "party": "Republican",
                    "chamber": "House",
                    "state": "TX",
                },
                "issuer": {"ticker": "MSFT", "name": "Microsoft Corp."},
                "traded_at": "2026-04-10",
                "filed_at": "2026-04-12",
                "reporting_gap_days": 2,
                "transaction_type": "sell",
                "amount_range_usd": [1001, 15000],
                "owner": "spouse",
                "source_url": "https://www.capitoltrades.com/trades/ct-2026-04-002",
            },
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_capitol_trades_parses_list() -> None:
    from app.services.source_clients.capitol_trades import fetch_capitol_trades

    respx.get(_TEST_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_capitol_trades(
            client=client, base_url=_TEST_URL
        )

    assert result.total_count == 2
    assert len(result.trades) == 2
    first = result.trades[0]
    assert first.trade_id == "ct-2026-04-001"
    assert first.politician.name == "Senator A. Smith"
    assert first.issuer.ticker == "AAPL"
    assert first.amount_range_usd == [15001, 50000]
    assert first.owner == "self"
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_capitol_trades_forwards_filters() -> None:
    from app.services.source_clients.capitol_trades import fetch_capitol_trades

    route = respx.get(_TEST_URL).mock(
        return_value=httpx.Response(200, json={"trades": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_capitol_trades(
            client=client, base_url=_TEST_URL, ticker="AAPL", page=3, page_size=50
        )

    sent = route.calls.last.request
    assert sent.url.params["ticker"] == "AAPL"
    assert sent.url.params["page"] == "3"
    assert sent.url.params["pageSize"] == "50"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_capitol_trades_handles_partial_records() -> None:
    from app.services.source_clients.capitol_trades import fetch_capitol_trades

    respx.get(_TEST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "trades": [
                    {
                        "trade_id": "ct-x",
                        "politician": {"name": "Sen. X"},
                        "issuer": {},
                        "traded_at": "2026-05-01",
                        "filed_at": "2026-05-02",
                        "transaction_type": "exchange",
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_capitol_trades(client=client, base_url=_TEST_URL)

    assert result.trades[0].issuer.ticker is None
    assert result.trades[0].amount_range_usd == []
    assert result.trades[0].owner is None
    assert result.trades[0].reporting_gap_days is None


def test_fetch_capitol_trades_requires_caller_supplied_base_url() -> None:
    """No speculative default exists — the function signature forces callers
    to wire a URL. The actual Capitol Trades endpoint is undocumented and
    not stable, so a default that 404s would silently break production."""
    import inspect

    from app.services.source_clients.capitol_trades import fetch_capitol_trades

    parameters = inspect.signature(fetch_capitol_trades).parameters
    assert parameters["base_url"].default is inspect.Parameter.empty


@pytest.mark.asyncio
@respx.mock
async def test_fetch_capitol_trades_500_retries_until_failure() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.capitol_trades import fetch_capitol_trades

    route = respx.get(_TEST_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_capitol_trades(client=client, base_url=_TEST_URL)

    assert route.call_count == 4


def test_capitol_trades_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import capitol_trades
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = capitol_trades._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert capitol_trades._rate_limiter() is limiter
