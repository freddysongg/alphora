"""End-to-end test against Alpaca's paper sandbox.

Skipped unless ALPACA_INTEGRATION=1 in the env. Requires real paper API
credentials. Places one $1-notional MARKET BUY of SPY, waits briefly,
queries it, then cancels (if still open) — leaving the paper account
in approximately its prior state.
"""
import asyncio
import os
import uuid
from decimal import Decimal

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import OrderRequest

_INTEGRATION = os.getenv("ALPACA_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not _INTEGRATION,
    reason="set ALPACA_INTEGRATION=1 to run Alpaca paper integration tests",
)


@pytest.mark.asyncio
async def test_paper_roundtrip_place_query_cancel() -> None:
    adapter = AlpacaAdapter.from_env()
    assert adapter.mode == "paper", "Refusing to run integration test in live mode"

    account = await adapter.get_account()
    assert Decimal(account.cash) >= Decimal("0"), "Paper account has invalid cash"

    quote = await adapter.get_quote("SPY")
    assert quote.last > Decimal("0"), "SPY quote is non-positive"

    client_id = f"phase0-{uuid.uuid4().hex[:8]}"
    request = OrderRequest(
        ticker="SPY",
        side="buy",
        quantity=Decimal("0.01"),  # fractional micro-position
        order_type="market",
        time_in_force="day",
        client_order_id=client_id,
    )
    response = await adapter.place_order(request)
    assert response.broker_order_id, "broker_order_id was empty"

    # Give the paper engine a moment to surface the order in list_orders.
    await asyncio.sleep(2)
    orders = await adapter.list_orders(status="all")
    matched = [o for o in orders if o.client_order_id == client_id]
    assert len(matched) == 1, f"expected one matching order, got {len(matched)}"

    # If still open, cancel; if already filled (likely for market), that's fine.
    if matched[0].status in ("new", "pending_new", "partially_filled"):
        await adapter.cancel_order(response.broker_order_id)
