"""Tests for the Ainvest-then-Capitol-Trades congressional-trade orchestrator.

Covers the failover decision tree: 5xx and rate-limit responses from Ainvest
trigger the Capitol Trades fallback; 4xx responses propagate (so auth /
quota issues stay visible); a missing fallback URL surfaces a distinct
error so deployments don't silently lose data."""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.services.source_clients import ainvest as ainvest_module
from app.services.source_clients import capitol_trades as capitol_module
from app.services.source_clients._http import (
    SourceClientHTTPError,
    SourceClientRateLimitError,
)
from app.services.source_clients.ainvest import (
    AinvestCongressData,
    AinvestCongressResponse,
    AinvestCongressTransaction,
)
from app.services.source_clients.capitol_trades import (
    CapitolTradesIssuer,
    CapitolTradesPolitician,
    CapitolTradesResponse,
    CapitolTradesTrade,
)
from app.services.strategies.funnel_research import congress_trading as orchestrator
from app.services.strategies.funnel_research.congress_trading import (
    CapitolTradesNotConfiguredError,
    fetch_congress_trades_for_ticker,
)


def _ainvest_response() -> AinvestCongressResponse:
    return AinvestCongressResponse(
        data=AinvestCongressData(
            data=[
                AinvestCongressTransaction(
                    name="Jane Doe",
                    party="D",
                    state="CA",
                    trade_date=date(2026, 4, 1),
                    filing_date=date(2026, 4, 15),
                    reporting_gap="14 days",
                    trade_type="purchase",
                    size="$1,001 - $15,000",
                ),
            ]
        ),
        status_code=200,
        status_msg="ok",
    )


def _capitol_response() -> CapitolTradesResponse:
    return CapitolTradesResponse(
        page=1,
        page_size=10,
        total_count=1,
        trades=[
            CapitolTradesTrade(
                trade_id="ct-1",
                politician=CapitolTradesPolitician(
                    name="Sen. A", party="D", chamber="Senate", state="CA"
                ),
                issuer=CapitolTradesIssuer(ticker="AAPL", name="Apple Inc."),
                traded_at=date(2026, 4, 1),
                filed_at=date(2026, 4, 10),
                reporting_gap_days=9,
                transaction_type="buy",
                amount_range_usd=[15001, 50000],
                owner="self",
            )
        ],
    )


@pytest.mark.asyncio
async def test_ainvest_happy_path_returns_ainvest_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ainvest(*, client, ticker):
        return _ainvest_response(), "a" * 64

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", fake_ainvest
    )

    async with httpx.AsyncClient() as client:
        result = await fetch_congress_trades_for_ticker(
            ticker="AAPL", client=client, capitol_trades_base_url="https://capitol.test"
        )

    assert result.source == "ainvest_congress"
    assert result.content_hash == "a" * 64
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ticker == "AAPL"
    assert trade.politician_name == "Jane Doe"
    assert trade.reporting_gap_days == 14


@pytest.mark.asyncio
async def test_ainvest_5xx_falls_back_to_capitol_trades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_ainvest(*, client, ticker):
        raise SourceClientHTTPError(
            status_code=503, url="https://ainvest.test", body_excerpt="upstream down"
        )

    async def fake_capitol(*, client, base_url, ticker, **_):
        assert base_url == "https://capitol.test"
        return _capitol_response(), "c" * 64

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", failing_ainvest
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", fake_capitol)

    async with httpx.AsyncClient() as client:
        result = await fetch_congress_trades_for_ticker(
            ticker="AAPL", client=client, capitol_trades_base_url="https://capitol.test"
        )

    assert result.source == "capitol_trades"
    assert result.content_hash == "c" * 64
    assert result.trades[0].external_id == "ct-1"
    assert result.trades[0].ticker == "AAPL"
    assert result.trades[0].amount_label == "$15,001 - $50,000"


@pytest.mark.asyncio
async def test_ainvest_rate_limit_falls_back_to_capitol_trades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rate_limited(*, client, ticker):
        raise SourceClientRateLimitError(
            url="https://ainvest.test", retry_after_seconds=5.0
        )

    async def fake_capitol(*, client, base_url, ticker, **_):
        return _capitol_response(), "c" * 64

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", rate_limited
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", fake_capitol)

    async with httpx.AsyncClient() as client:
        result = await fetch_congress_trades_for_ticker(
            ticker="AAPL", client=client, capitol_trades_base_url="https://capitol.test"
        )

    assert result.source == "capitol_trades"


@pytest.mark.asyncio
async def test_ainvest_4xx_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4xx propagates because it signals an auth/quota issue that needs
    attention — silently falling back would mask deployment problems."""
    async def unauthorised(*, client, ticker):
        raise SourceClientHTTPError(
            status_code=401, url="https://ainvest.test", body_excerpt="bad token"
        )

    async def fake_capitol(*, client, base_url, ticker, **_):
        raise AssertionError("fallback must not fire on 4xx")

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", unauthorised
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", fake_capitol)

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_congress_trades_for_ticker(
                ticker="AAPL",
                client=client,
                capitol_trades_base_url="https://capitol.test",
            )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_fallback_required_but_url_missing_raises_distinct_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_ainvest(*, client, ticker):
        raise SourceClientHTTPError(
            status_code=502, url="https://ainvest.test", body_excerpt="bad gateway"
        )

    async def fake_capitol(*, client, base_url, ticker, **_):
        raise AssertionError("Capitol Trades must not be called when URL is missing")

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", failing_ainvest
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", fake_capitol)

    async with httpx.AsyncClient() as client:
        with pytest.raises(CapitolTradesNotConfiguredError):
            await fetch_congress_trades_for_ticker(
                ticker="AAPL", client=client, capitol_trades_base_url=None
            )


@pytest.mark.asyncio
async def test_both_sources_failing_propagates_capitol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_ainvest(*, client, ticker):
        raise SourceClientHTTPError(
            status_code=500, url="https://ainvest.test", body_excerpt="boom"
        )

    async def failing_capitol(*, client, base_url, ticker, **_):
        raise SourceClientHTTPError(
            status_code=500, url="https://capitol.test", body_excerpt="also boom"
        )

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", failing_ainvest
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", failing_capitol)

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_congress_trades_for_ticker(
                ticker="AAPL",
                client=client,
                capitol_trades_base_url="https://capitol.test",
            )

    assert exc_info.value.url == "https://capitol.test"


@pytest.mark.asyncio
async def test_capitol_payload_normalises_reporting_gap_from_dates_when_field_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Capitol Trades omits `reporting_gap_days`, the orchestrator computes
    it from `filed_at - traded_at` so downstream extraction always sees a value."""

    async def failing_ainvest(*, client, ticker):
        raise SourceClientHTTPError(
            status_code=503, url="https://ainvest.test", body_excerpt="down"
        )

    async def fake_capitol(*, client, base_url, ticker, **_):
        return (
            CapitolTradesResponse(
                trades=[
                    CapitolTradesTrade(
                        trade_id="ct-2",
                        politician=CapitolTradesPolitician(name="Rep. B"),
                        issuer=CapitolTradesIssuer(ticker="MSFT"),
                        traded_at=date(2026, 1, 1),
                        filed_at=date(2026, 1, 21),
                        reporting_gap_days=None,
                        transaction_type="sell",
                        amount_range_usd=[],
                    )
                ]
            ),
            "c" * 64,
        )

    monkeypatch.setattr(
        orchestrator, "fetch_ainvest_congress_transactions", failing_ainvest
    )
    monkeypatch.setattr(orchestrator, "fetch_capitol_trades", fake_capitol)

    async with httpx.AsyncClient() as client:
        result = await fetch_congress_trades_for_ticker(
            ticker="MSFT", client=client, capitol_trades_base_url="https://capitol.test"
        )

    assert result.trades[0].reporting_gap_days == 20
    assert result.trades[0].amount_label == "unknown"


def test_real_source_client_imports_are_re_exported() -> None:
    """Sanity check that the orchestrator imports the actual source-client
    functions, not stand-in stubs — so production code paths are exercised."""
    assert (
        orchestrator.fetch_ainvest_congress_transactions
        is ainvest_module.fetch_ainvest_congress_transactions
    )
    assert orchestrator.fetch_capitol_trades is capitol_module.fetch_capitol_trades
