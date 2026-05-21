"""Thin pandas-ta wrappers for the indicators used by the strategy engine.

Nothing outside this package imports pandas-ta directly. The strategy
engine consumes Series/DataFrames produced here; the wrappers exist so
we can swap pandas-ta for another library in one place if needed and so
parameter naming stays consistent across the codebase.
"""
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
import pandas_ta as ta

__all__ = ["ema"]


def ema(close: pd.Series, *, period: int) -> pd.Series:
    """Exponential moving average.

    Returns a Series aligned to `close`; positions before index `period - 1`
    are NaN (warmup). Seeded with the SMA of the first `period` values,
    matching the convention in the source Node bot's `lib/indicators.js`.
    """
    result = ta.ema(close, length=period)
    if result is None:
        raise ValueError(
            f"ema returned None for period={period}, len(close)={len(close)}; "
            "input series is shorter than the warmup window"
        )
    return result
