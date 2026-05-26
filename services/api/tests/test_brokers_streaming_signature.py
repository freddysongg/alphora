from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import Bar, BrokerAdapter, Order


def test_stream_bars_protocol_method_is_sync_returning_async_iterator() -> None:
    """The Protocol's stream_bars must be a regular (non-coroutine) method.
    Calling it should return an AsyncIterator immediately, not a coroutine."""
    sig = inspect.signature(BrokerAdapter.stream_bars)
    assert not inspect.iscoroutinefunction(BrokerAdapter.stream_bars), (
        "stream_bars must not be `async def` — it returns an AsyncIterator directly"
    )
    annotation = sig.return_annotation
    assert annotation is AsyncIterator[Bar] or "AsyncIterator[" in str(annotation), (
        f"stream_bars return annotation must be AsyncIterator[Bar], got {annotation!r}"
    )


def test_stream_order_updates_protocol_method_is_sync_returning_async_iterator() -> None:
    sig = inspect.signature(BrokerAdapter.stream_order_updates)
    assert not inspect.iscoroutinefunction(BrokerAdapter.stream_order_updates), (
        "stream_order_updates must not be `async def`"
    )
    annotation = sig.return_annotation
    assert annotation is AsyncIterator[Order] or "AsyncIterator[" in str(annotation)


def test_alpaca_adapter_stream_bars_impl_is_sync_returning_async_iterator() -> None:
    """AlpacaAdapter.stream_bars must match the Protocol — sync, returns AsyncIterator."""
    assert not inspect.iscoroutinefunction(AlpacaAdapter.stream_bars), (
        "AlpacaAdapter.stream_bars must not be `async def` — it returns an "
        "AsyncIterator constructed from an internal async generator"
    )


def test_alpaca_adapter_stream_bars_returns_async_iterator_synchronously() -> None:
    """Calling stream_bars on the adapter must produce an AsyncIterator
    object immediately (no await). Smoke-tests the contract without
    actually subscribing to a feed."""
    class _StubTradingClient:
        pass

    class _StubDataClient:
        pass

    adapter = AlpacaAdapter(
        trading_client=_StubTradingClient(),  # type: ignore[arg-type]
        data_client=_StubDataClient(),  # type: ignore[arg-type]
        mode="paper",
    )
    iterator = adapter.stream_bars(["SPY"], "1min")
    assert hasattr(iterator, "__aiter__"), (
        f"stream_bars must return an AsyncIterator, got {type(iterator)!r}"
    )
    assert not asyncio.iscoroutine(iterator), (
        "stream_bars must return an AsyncIterator immediately, not a coroutine"
    )


def test_alpaca_adapter_stream_order_updates_returns_async_iterator_synchronously() -> None:
    """Calling stream_order_updates on the adapter must produce an
    AsyncIterator object immediately (no await). Smoke-tests the contract
    without actually subscribing to a feed."""
    class _StubTradingClient:
        pass

    class _StubDataClient:
        pass

    adapter = AlpacaAdapter(
        trading_client=_StubTradingClient(),  # type: ignore[arg-type]
        data_client=_StubDataClient(),  # type: ignore[arg-type]
        mode="paper",
    )
    iterator = adapter.stream_order_updates()
    assert hasattr(iterator, "__aiter__"), (
        f"stream_order_updates must return an AsyncIterator, got {type(iterator)!r}"
    )
    assert not asyncio.iscoroutine(iterator), (
        "stream_order_updates must return an AsyncIterator immediately, not a coroutine"
    )
