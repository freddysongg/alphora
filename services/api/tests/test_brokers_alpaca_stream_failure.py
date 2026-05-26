from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import Bar, Order


class _FakeBarStream:
    """Stub `StockDataStream` whose `_run_forever` can raise or enqueue and return."""

    def __init__(
        self,
        *,
        run_behavior: Callable[[Callable[[object], Awaitable[None]]], Awaitable[None]],
    ) -> None:
        self._run_behavior = run_behavior
        self._callback: Callable[[object], Awaitable[None]] | None = None
        self.close_called = False

    def subscribe_bars(
        self, callback: Callable[[object], Awaitable[None]], *tickers: str
    ) -> None:
        self._callback = callback

    async def _run_forever(self) -> None:
        assert self._callback is not None, "subscribe_bars must run before _run_forever"
        await self._run_behavior(self._callback)

    async def close(self) -> None:
        self.close_called = True


class _FakeOrderStream:
    """Stub `TradingStream` whose `_run_forever` can raise or enqueue and return."""

    def __init__(
        self,
        *,
        run_behavior: Callable[[Callable[[object], Awaitable[None]]], Awaitable[None]],
    ) -> None:
        self._run_behavior = run_behavior
        self._callback: Callable[[object], Awaitable[None]] | None = None
        self.close_called = False

    def subscribe_trade_updates(
        self, callback: Callable[[object], Awaitable[None]]
    ) -> None:
        self._callback = callback

    async def _run_forever(self) -> None:
        assert self._callback is not None, (
            "subscribe_trade_updates must run before _run_forever"
        )
        await self._run_behavior(self._callback)

    async def close(self) -> None:
        self.close_called = True


def _build_fake_bar(symbol: str) -> MagicMock:
    fake_bar = MagicMock()
    fake_bar.symbol = symbol
    fake_bar.open = 100.0
    fake_bar.high = 100.5
    fake_bar.low = 99.5
    fake_bar.close = 100.2
    fake_bar.volume = 10000
    fake_bar.vwap = 100.1
    fake_bar.timestamp = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    return fake_bar


def _build_fake_order_event(order_id: str) -> MagicMock:
    fake_order = MagicMock()
    fake_order.id = order_id
    fake_order.client_order_id = f"client-{order_id}"
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
    return fake_event


def _build_adapter() -> AlpacaAdapter:
    return AlpacaAdapter(
        trading_client=MagicMock(), data_client=MagicMock(), mode="paper"
    )


async def _collect_with_timeout(
    iterator: AsyncGenerator[object, None], timeout: float
) -> list[object]:
    collected: list[object] = []

    async def _drain() -> None:
        async for item in iterator:
            collected.append(item)

    await asyncio.wait_for(_drain(), timeout=timeout)
    return collected


@pytest.mark.asyncio
async def test_stream_bars_propagates_run_forever_exception() -> None:
    """If `_run_forever` raises, the bar stream must surface the exception
    instead of hanging on `queue.get()`."""

    async def _raise(_callback: Callable[[object], Awaitable[None]]) -> None:
        raise RuntimeError("auth failed")

    fake_stream = _FakeBarStream(run_behavior=_raise)
    adapter = _build_adapter()
    adapter._stock_data_stream_factory = lambda: fake_stream  # type: ignore[method-assign,assignment,return-value]

    iterator = cast(
        AsyncGenerator[Bar, None], adapter.stream_bars(["SPY"], "1min")
    )

    with pytest.raises(RuntimeError, match="auth failed"):
        await _collect_with_timeout(
            cast(AsyncGenerator[object, None], iterator), timeout=2.0
        )
    assert fake_stream.close_called is True


@pytest.mark.asyncio
async def test_stream_bars_ends_cleanly_when_run_forever_returns() -> None:
    """If `_run_forever` enqueues a few bars then returns, the stream must
    drain them and end without exception."""

    async def _enqueue_two_then_return(
        callback: Callable[[object], Awaitable[None]],
    ) -> None:
        await callback(_build_fake_bar("SPY"))
        await callback(_build_fake_bar("SPY"))

    fake_stream = _FakeBarStream(run_behavior=_enqueue_two_then_return)
    adapter = _build_adapter()
    adapter._stock_data_stream_factory = lambda: fake_stream  # type: ignore[method-assign,assignment,return-value]

    iterator = cast(
        AsyncGenerator[Bar, None], adapter.stream_bars(["SPY"], "1min")
    )

    collected = await _collect_with_timeout(
        cast(AsyncGenerator[object, None], iterator), timeout=2.0
    )
    assert len(collected) == 2
    assert all(isinstance(item, Bar) for item in collected)
    assert fake_stream.close_called is True


@pytest.mark.asyncio
async def test_stream_order_updates_propagates_run_forever_exception() -> None:
    """If `_run_forever` raises, the order-update stream must surface the
    exception instead of hanging on `queue.get()`."""

    async def _raise(_callback: Callable[[object], Awaitable[None]]) -> None:
        raise RuntimeError("auth failed")

    fake_stream = _FakeOrderStream(run_behavior=_raise)
    adapter = _build_adapter()
    adapter._trading_stream_factory = lambda: fake_stream  # type: ignore[method-assign,assignment,return-value]

    iterator = cast(
        AsyncGenerator[Order, None], adapter.stream_order_updates()
    )

    with pytest.raises(RuntimeError, match="auth failed"):
        await _collect_with_timeout(
            cast(AsyncGenerator[object, None], iterator), timeout=2.0
        )
    assert fake_stream.close_called is True


@pytest.mark.asyncio
async def test_stream_order_updates_ends_cleanly_when_run_forever_returns() -> None:
    """If `_run_forever` enqueues a few orders then returns, the stream must
    drain them and end without exception."""

    async def _enqueue_two_then_return(
        callback: Callable[[object], Awaitable[None]],
    ) -> None:
        await callback(_build_fake_order_event("ord-1"))
        await callback(_build_fake_order_event("ord-2"))

    fake_stream = _FakeOrderStream(run_behavior=_enqueue_two_then_return)
    adapter = _build_adapter()
    adapter._trading_stream_factory = lambda: fake_stream  # type: ignore[method-assign,assignment,return-value]

    iterator = cast(
        AsyncGenerator[Order, None], adapter.stream_order_updates()
    )

    collected = await _collect_with_timeout(
        cast(AsyncGenerator[object, None], iterator), timeout=2.0
    )
    assert len(collected) == 2
    assert all(isinstance(item, Order) for item in collected)
    assert [cast(Order, item).broker_order_id for item in collected] == [
        "ord-1",
        "ord-2",
    ]
    assert fake_stream.close_called is True
