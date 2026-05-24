from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import OrderRequest
from app.brokers.errors import BrokerError, BrokerOrderRejected, BrokerTransientError


def test_broker_error_is_base_exception() -> None:
    assert issubclass(BrokerError, Exception)
    assert issubclass(BrokerOrderRejected, BrokerError)
    assert issubclass(BrokerTransientError, BrokerError)


def test_broker_order_rejected_carries_reason_and_request() -> None:
    req = OrderRequest(
        ticker="SPY", side="buy", quantity=Decimal("1"),
        order_type="market", time_in_force="day",
    )
    err = BrokerOrderRejected("insufficient_funds", request=req)
    assert err.reason == "insufficient_funds"
    assert err.request is req
    assert "insufficient_funds" in str(err)


@pytest.mark.asyncio
async def test_alpaca_place_order_wraps_apierror_as_broker_order_rejected() -> None:
    """When alpaca-py raises APIError, the adapter wraps it as BrokerOrderRejected."""
    from alpaca.common.exceptions import APIError

    trading_client = MagicMock()
    trading_client.submit_order.side_effect = APIError(  # type: ignore[no-untyped-call]
        '{"code": 40010001, "message": "insufficient buying power"}'
    )
    adapter = AlpacaAdapter(
        trading_client=trading_client,
        data_client=MagicMock(),
        mode="paper",
    )
    req = OrderRequest(
        ticker="SPY", side="buy", quantity=Decimal("1"),
        order_type="market", time_in_force="day",
    )
    with pytest.raises(BrokerOrderRejected) as exc_info:
        await adapter.place_order(req)
    assert "insufficient" in str(exc_info.value).lower()
    assert exc_info.value.request is req


@pytest.mark.asyncio
async def test_alpaca_place_order_wraps_connection_error_as_transient() -> None:
    """Network-level errors map to BrokerTransientError (retriable)."""
    import httpx

    trading_client = MagicMock()
    trading_client.submit_order.side_effect = httpx.ConnectError("network down")
    adapter = AlpacaAdapter(
        trading_client=trading_client,
        data_client=MagicMock(),
        mode="paper",
    )
    req = OrderRequest(
        ticker="SPY", side="buy", quantity=Decimal("1"),
        order_type="market", time_in_force="day",
    )
    with pytest.raises(BrokerTransientError):
        await adapter.place_order(req)


@pytest.mark.asyncio
async def test_alpaca_cancel_order_wraps_apierror() -> None:
    from alpaca.common.exceptions import APIError

    trading_client = MagicMock()
    trading_client.cancel_order_by_id.side_effect = APIError(  # type: ignore[no-untyped-call]
        '{"code": 42210000, "message": "order not found"}'
    )
    adapter = AlpacaAdapter(
        trading_client=trading_client,
        data_client=MagicMock(),
        mode="paper",
    )
    with pytest.raises(BrokerOrderRejected):
        await adapter.cancel_order("nonexistent-id")
