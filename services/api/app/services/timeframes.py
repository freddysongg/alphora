"""Resample a 1-minute bar frame into a higher timeframe.

Phase 3 needs multi-timeframe support in `simulate()`: at each primary
bar `i`, the backtest engine must hand the strategy a `secondary_bars`
dict whose values are the running secondary-timeframe view including the
in-flight bucket (the bucket that currently contains bar `i`). This
matches the source bot's `updateAggregatedBars()` in `lib/backtest.js`:
`closed.concat([current])`. Confluence-Long requires this exact shape
for golden parity.

The implementation uses pandas `.resample(rule, label='left',
closed='left')` which aligns buckets to UTC-epoch multiples of the
target duration -- identical to the source bot's
`Math.floor(barTime / bucketMs) * bucketMs`. Empty buckets (overnight
gaps) are dropped so the secondary view contains only bars with data.

Cost: O(N) per call. Called once per primary bar from `simulate()`, so
the whole-backtest cost is O(N * secondary_count).
"""
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.brokers.base import Timeframe

_COLUMNS = ["open", "high", "low", "close", "volume"]

_TIMEFRAME_TO_PANDAS_RULE: dict[Timeframe, str] = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "1h": "1h",
    "1d": "1D",
}


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {col: pd.Series(dtype="float64") for col in _COLUMNS},
        index=pd.DatetimeIndex([], tz="UTC", name="timestamp"),
    )


def resample_bars_to_timeframe(
    primary_bars: pd.DataFrame, target_timeframe: Timeframe
) -> pd.DataFrame:
    """Resample a 1-min OHLCV frame into `target_timeframe` buckets.

    The trailing row is the in-flight bucket containing the most recent
    primary bar -- i.e., `close` is the last seen 1-min close, `volume`
    is partial-bucket cumulative, etc. This matches the source bot's
    `updateAggregatedBars` semantics.

    Empty buckets (e.g., overnight gaps) are dropped so the secondary
    view contains only the data the strategy will see. Returns a frame
    with columns `open, high, low, close, volume` and a UTC
    `DatetimeIndex`.
    """
    if target_timeframe not in _TIMEFRAME_TO_PANDAS_RULE:
        raise ValueError(f"unsupported timeframe: {target_timeframe!r}")
    if primary_bars.empty:
        return _empty_frame()

    rule = _TIMEFRAME_TO_PANDAS_RULE[target_timeframe]
    resampled = primary_bars.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    resampled = resampled.dropna(subset=["open"])
    return resampled[_COLUMNS]


__all__ = ["resample_bars_to_timeframe"]
