from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import Order


@pytest.mark.asyncio
async def test_stream_order_updates_yields_translated_orders() -> None:
    trading = MagicMock()
    data = MagicMock()
    adapter = AlpacaAdapter(trading_client=trading, data_client=data, mode="paper")

    fake_stream = MagicMock()
    fake_stream.subscribe_trade_updates = MagicMock()
    async def _block_forever() -> None:
        await asyncio.sleep(10)

    fake_stream._run_forever = AsyncMock(side_effect=_block_forever)
    fake_stream.close = AsyncMock()
    adapter._trading_stream_factory = lambda: fake_stream  # type: ignore[method-assign]

    iterator = adapter.stream_order_updates()

    async def _consume_one() -> Order:
        return await iterator.__anext__()

    consume_task = asyncio.create_task(_consume_one())
    for _ in range(50):
        if fake_stream.subscribe_trade_updates.called:
            break
        await asyncio.sleep(0.01)
    callback = fake_stream.subscribe_trade_updates.call_args[0][0]

    fake_order = MagicMock()
    fake_order.id = "ord-1"
    fake_order.client_order_id = "client-1"
    fake_order.symbol = "SPY"
    fake_order.side = "buy"
    fake_order.qty = 1
    fake_order.filled_qty = 1
    fake_order.order_type = "market"
    fake_order.time_in_force = "day"
    fake_order.status = "filled"
    fake_order.limit_price = None
    fake_order.stop_price = None
    fake_order.filled_avg_price = 500.0
    fake_order.submitted_at = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    fake_order.filled_at = datetime(2026, 6, 15, 13, 30, 5, tzinfo=UTC)
    fake_order.canceled_at = None

    fake_event = MagicMock()
    fake_event.order = fake_order
    await callback(fake_event)

    order = await asyncio.wait_for(consume_task, timeout=2.0)
    assert order.broker_order_id == "ord-1"
    assert order.ticker == "SPY"
    assert order.status == "filled"
    assert order.filled_quantity == Decimal("1")
    assert order.avg_fill_price == Decimal("500.0")
    await cast(AsyncGenerator[Order, None], iterator).aclose()
