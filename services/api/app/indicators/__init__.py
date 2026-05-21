"""Thin pandas-ta wrappers for the indicators used by the strategy engine.

Nothing outside this package imports pandas-ta directly. The strategy
engine consumes Series/DataFrames produced here; the wrappers exist so
we can swap pandas-ta for another library in one place if needed and so
parameter naming stays consistent across the codebase.
"""
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
import pandas_ta as ta

__all__ = ["ema", "macd", "rsi"]


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


def macd(
    close: pd.Series, *, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD(fast, slow, signal) → (macd_line, signal_line, histogram).

    Each Series is aligned to `close`; warmup positions are NaN. Matches
    the source bot's `macd()` in `lib/indicators.js`: fast/slow are
    EMAs of `close`, signal is an EMA of `(emaFast - emaSlow)` on the
    non-NaN tail, histogram = macd_line - signal_line.
    """
    df = ta.macd(close, fast=fast, slow=slow, signal=signal)
    if df is None:
        raise ValueError(
            f"macd returned None for fast={fast}, slow={slow}, signal={signal}, "
            f"len(close)={len(close)}; input series is shorter than the warmup window"
        )
    macd_line: pd.Series = df[f"MACD_{fast}_{slow}_{signal}"]
    histogram: pd.Series = df[f"MACDh_{fast}_{slow}_{signal}"]
    signal_line: pd.Series = df[f"MACDs_{fast}_{slow}_{signal}"]
    return macd_line, signal_line, histogram


def rsi(close: pd.Series, *, period: int = 14) -> pd.Series:
    """Wilder's RSI on `close`.

    Returns a Series aligned to `close`; positions before index `period`
    are NaN. Default period 14 matches the source bot.
    """
    result = ta.rsi(close, length=period)
    if result is None:
        raise ValueError(
            f"rsi returned None for period={period}, len(close)={len(close)}; "
            "input series is shorter than the warmup window"
        )
    # pandas-ta 0.4.x emits a value starting at index 1, but the source
    # bot's `rsi` in lib/indicators.js leaves indices 0..period-1
    # undefined and writes the first value at index `period`. Mask the
    # warmup region to match — required for the Task 14 golden-output
    # regression to pass on the early bars.
    masked = result.copy()
    masked.iloc[:period] = float("nan")
    return masked
