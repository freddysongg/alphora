from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import Bar


@pytest.mark.asyncio
async def test_stream_bars_yields_bars_from_callback() -> None:
    """Smoke-test the queue wiring: when the underlying stream invokes
    the registered callback, the async generator yields the equivalent
    `Bar` model."""
    trading = MagicMock()
    data = MagicMock()
    adapter = AlpacaAdapter(trading_client=trading, data_client=data, mode="paper")

    fake_stream = MagicMock()
    fake_stream.subscribe_bars = MagicMock()
    async def _block_forever() -> None:
        await asyncio.sleep(10)

    fake_stream._run_forever = AsyncMock(side_effect=_block_forever)
    fake_stream.close = AsyncMock()
    adapter._stock_data_stream_factory = lambda: fake_stream  # type: ignore[method-assign]

    iterator = cast(
        AsyncGenerator[Bar, None], adapter.stream_bars(["SPY"], "1min")
    )

    async def _consume_one() -> Bar:
        return await iterator.__anext__()

    consume_task = asyncio.create_task(_consume_one())
    for _ in range(50):
        if fake_stream.subscribe_bars.called:
            break
        await asyncio.sleep(0.01)
    assert fake_stream.subscribe_bars.called
    callback = fake_stream.subscribe_bars.call_args[0][0]

    fake_bar = MagicMock()
    fake_bar.symbol = "SPY"
    fake_bar.open = 100.0
    fake_bar.high = 100.5
    fake_bar.low = 99.5
    fake_bar.close = 100.2
    fake_bar.volume = 10000
    fake_bar.vwap = 100.1
    fake_bar.timestamp = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)

    await callback(fake_bar)
    bar = await asyncio.wait_for(consume_task, timeout=2.0)
    assert bar.ticker == "SPY"
    assert bar.timeframe == "1min"
    assert bar.open == Decimal("100.0")
    assert bar.high == Decimal("100.5")
    assert bar.low == Decimal("99.5")
    assert bar.close == Decimal("100.2")
    assert bar.volume == Decimal("10000")
    await iterator.aclose()


@pytest.mark.asyncio
async def test_stream_bars_subscribe_uses_correct_symbol_list() -> None:
    trading = MagicMock()
    data = MagicMock()
    adapter = AlpacaAdapter(trading_client=trading, data_client=data, mode="paper")
    fake_stream = MagicMock()
    fake_stream.subscribe_bars = MagicMock()
    async def _block_forever() -> None:
        await asyncio.sleep(10)

    fake_stream._run_forever = AsyncMock(side_effect=_block_forever)
    fake_stream.close = AsyncMock()
    adapter._stock_data_stream_factory = lambda: fake_stream  # type: ignore[method-assign]

    iterator = cast(
        AsyncGenerator[Bar, None], adapter.stream_bars(["SPY", "QQQ"], "1min")
    )

    async def _await_setup() -> None:
        try:
            await asyncio.wait_for(iterator.__anext__(), timeout=0.1)
        except TimeoutError:
            pass

    await _await_setup()
    for _ in range(50):
        if fake_stream.subscribe_bars.called:
            break
        await asyncio.sleep(0.01)
    args = fake_stream.subscribe_bars.call_args
    assert args[0][1] == "SPY"
    assert args[0][2] == "QQQ"
    await iterator.aclose()


@pytest.mark.asyncio
async def test_stream_bars_awaits_run_forever_not_sync_run() -> None:
    """`StockDataStream.run()` is sync and internally calls `asyncio.run()`,
    which raises when invoked from inside an existing event loop. The adapter
    must schedule the underlying `_run_forever()` coroutine instead."""
    trading = MagicMock()
    data = MagicMock()
    adapter = AlpacaAdapter(trading_client=trading, data_client=data, mode="paper")
    fake_stream = MagicMock()
    fake_stream.subscribe_bars = MagicMock()
    async def _block_forever() -> None:
        await asyncio.sleep(10)

    fake_stream._run_forever = AsyncMock(side_effect=_block_forever)
    fake_stream.run = MagicMock(side_effect=AssertionError("must not call sync run()"))
    fake_stream.close = AsyncMock()
    adapter._stock_data_stream_factory = lambda: fake_stream  # type: ignore[method-assign]

    iterator = cast(
        AsyncGenerator[Bar, None], adapter.stream_bars(["SPY"], "1min")
    )
    try:
        await asyncio.wait_for(iterator.__anext__(), timeout=0.1)
    except TimeoutError:
        pass
    await asyncio.sleep(0.02)
    fake_stream._run_forever.assert_awaited()
    fake_stream.run.assert_not_called()
    await iterator.aclose()
