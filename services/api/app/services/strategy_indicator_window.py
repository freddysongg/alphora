"""Bounded per-runner bar buffer.

The strategy runner maintains one of these per (strategy_key, ticker)
pair. Each appended bar drops the oldest if at capacity. `to_frame()`
returns the buffer as a pandas DataFrame in the canonical OHLCV column
order that all strategies expect. Capacity bound = INDICATOR_WINDOW_BARS
(~12x the largest indicator period in v1), keeping per-evaluate cost
O(window_size) ~ constant instead of O(N) per bar.

This is Phase 4's "incremental indicator state" interpretation: rather
than rewriting all 6 strategies into a scalar-update API, bound the
historical window the strategy sees. Cost goes from O(N^2) total to
O(N * window_size) -- same asymptotic improvement, zero strategy code
change.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable

import pandas as pd  # type: ignore[import-untyped]

from app.brokers.base import Bar

INDICATOR_WINDOW_BARS: int = 250


class BoundedBarBuffer:
    """Fixed-capacity FIFO of `Bar` instances.

    `max_size` is the upper bound on retained bars; older bars are
    discarded as new ones arrive. Use `to_frame()` to materialize as a
    pandas DataFrame for indicator math.
    """

    def __init__(self, max_size: int = INDICATOR_WINDOW_BARS) -> None:
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self.max_size: int = max_size
        self._bars: deque[Bar] = deque(maxlen=max_size)

    def append(self, bar: Bar) -> None:
        self._bars.append(bar)

    def seed(self, bars: Iterable[Bar]) -> None:
        """Bulk-load historical bars. Useful on runner startup so the
        first live evaluate() has indicator warmup already done. Bars
        beyond `max_size` are silently dropped (deque retains last
        `max_size`)."""
        for bar in bars:
            self._bars.append(bar)

    def __len__(self) -> int:
        return len(self._bars)

    def to_frame(self) -> pd.DataFrame:
        """Materialize as a UTC-indexed OHLCV DataFrame.

        Column order matches every strategy's expectations: open, high,
        low, close, volume. Empty buffer returns an empty DataFrame
        with the same column shape so strategies can be indexed
        defensively.
        """
        if not self._bars:
            return pd.DataFrame(
                {col: [] for col in ("open", "high", "low", "close", "volume")},
                index=pd.DatetimeIndex([], tz="UTC"),
            )
        idx = pd.DatetimeIndex([b.as_of for b in self._bars], tz="UTC")
        return pd.DataFrame(
            {
                "open": [float(b.open) for b in self._bars],
                "high": [float(b.high) for b in self._bars],
                "low": [float(b.low) for b in self._bars],
                "close": [float(b.close) for b in self._bars],
                "volume": [float(b.volume) for b in self._bars],
            },
            index=idx,
        )


__all__ = ["BoundedBarBuffer", "INDICATOR_WINDOW_BARS"]
