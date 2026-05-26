"""Thin pandas-ta wrappers for the indicators used by the strategy engine.

Nothing outside this package imports pandas-ta directly. The strategy
engine consumes Series/DataFrames produced here; the wrappers exist so
we can swap pandas-ta for another library in one place if needed and so
parameter naming stays consistent across the codebase.
"""
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
import pandas_ta as ta

__all__ = ["adx", "atr", "bollinger", "ema", "macd", "rsi", "vwap"]


def adx(bars: pd.DataFrame, *, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder) on a bars DataFrame.

    `bars` must have columns `high`, `low`, `close`. Returns a Series of
    ADX values aligned to `bars.index`; positions before `2 * period` are
    NaN. Default period 14 matches the source bot.
    """
    df = ta.adx(high=bars["high"], low=bars["low"], close=bars["close"], length=period)
    if df is None:
        raise ValueError(
            f"adx returned None for period={period}, len(bars)={len(bars)}; "
            "input frame is shorter than the warmup window"
        )
    result: pd.Series = df[f"ADX_{period}"]
    # pandas-ta 0.4.x emits a value starting at index period-1, but the
    # source bot's `adx` in lib/indicators.js leaves indices
    # 0..(2*period - 1) undefined and writes the first value at index
    # 2*period. Mask the warmup region to match — required for the Task
    # 14 golden-output regression to pass on the early bars.
    masked = result.copy()
    masked.iloc[: 2 * period] = float("nan")
    return masked


def atr(bars: pd.DataFrame, *, period: int = 14) -> pd.Series:
    """Average True Range (Wilder) on a bars DataFrame.

    `bars` must have columns `high`, `low`, `close`. Returns a Series of
    ATR values aligned to `bars.index`; positions before `period` are
    NaN. Default period 14 matches the source bot.

    Unused by the MACD+RSI+ADX strategy; included here because the
    `TrailSpec` returned by other strategies (Phase 3) will be evaluated
    using this wrapper inside the runner.
    """
    result = ta.atr(high=bars["high"], low=bars["low"], close=bars["close"], length=period)
    if result is None:
        raise ValueError(
            f"atr returned None for period={period}, len(bars)={len(bars)}; "
            "input frame is shorter than the warmup window"
        )
    # pandas-ta 0.4.x emits a value starting at index period-1, but the
    # source bot's `atr` in lib/indicators.js leaves indices 0..period-1
    # undefined and writes the first value at index `period`. Mask the
    # warmup region to match.
    masked = result.copy()
    masked.iloc[:period] = float("nan")
    return masked


def bollinger(
    close: pd.Series, *, period: int = 20, mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands -> (middle, upper, lower) aligned to `close`.

    Uses **population** standard deviation (divisor `N`, not `N-1`) to
    match the source bot's `bollinger()` in `lib/indicators.js`. Warmup
    positions (indices 0..period-2) are NaN.

    Vectorised via `close.rolling(period).mean()` and `.std(ddof=0)`.
    `ddof=0` is population stddev, mathematically identical to the source
    bot's `Math.sqrt(varSum / period)`. Pandas' rolling is C-backed and
    much faster than the prior Python double-loop, which mattered when
    the strategy was called N times inside the backtest simulator with
    growing prefix slices.
    """
    if len(close) < period:
        return (
            pd.Series(float("nan"), index=close.index, dtype="float64"),
            pd.Series(float("nan"), index=close.index, dtype="float64"),
            pd.Series(float("nan"), index=close.index, dtype="float64"),
        )
    middle = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    upper = middle + mult * sd
    lower = middle - mult * sd
    return middle.astype("float64"), upper.astype("float64"), lower.astype("float64")


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

    Implemented directly instead of via `ta.rsi`: pandas-ta 0.4.x uses
    EWM smoothing seeded from the first diff, which diverges from the
    source bot's SMA-seeded Wilder smoothing (lib/indicators.js:71-93).
    The Task 14 golden-output regression requires bar-for-bar parity, so
    we port the JS algorithm exactly: seed `avg_gain`/`avg_loss` with the
    SMA of the first `period` diffs, then apply Wilder smoothing
    `avg = (avg * (period - 1) + step) / period` from index `period + 1`.
    """
    n = len(close)
    out = pd.Series(float("nan"), index=close.index, dtype="float64")
    if n <= period:
        return out

    values = close.to_numpy(dtype="float64", copy=False)
    gain_sum = 0.0
    loss_sum = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gain_sum += diff
        else:
            loss_sum -= diff
    avg_gain = gain_sum / period
    avg_loss = loss_sum / period
    out.iloc[period] = (
        100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    )

    for i in range(period + 1, n):
        diff = values[i] - values[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out.iloc[i] = (
            100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
        )

    return out


def vwap(bars: pd.DataFrame) -> pd.Series:
    """Session-resetting VWAP (RTH-only), matching source bot's `vwap()`.

    Resets the cumulative pv/v accumulator at each new ET RTH session
    open (09:30 America/New_York). Returns NaN for bars outside RTH so
    strategies can't accidentally trade off overnight-accumulated values.
    Zero/missing volume falls back to `1.0` (matches `b.v || 1` in JS).

    `bars` must have a UTC `DatetimeIndex` and columns `high`, `low`,
    `close`, `volume`.
    """
    from app.services.market_clock import RTH_CLOSE_ET_MIN, RTH_OPEN_ET_MIN, to_et

    n = len(bars)
    result = pd.Series(float("nan"), index=bars.index, dtype="float64")
    if n == 0:
        return result

    highs = bars["high"].astype(float).to_numpy()
    lows = bars["low"].astype(float).to_numpy()
    closes = bars["close"].astype(float).to_numpy()
    volumes = bars["volume"].astype(float).to_numpy()

    sum_pv = 0.0
    sum_v = 0.0
    current_day: str | None = None
    for i in range(n):
        clock = to_et(bars.index[i])
        in_rth = RTH_OPEN_ET_MIN <= clock.minutes < RTH_CLOSE_ET_MIN
        if in_rth and clock.day != current_day:
            sum_pv = 0.0
            sum_v = 0.0
            current_day = clock.day
        if in_rth:
            typical = (highs[i] + lows[i] + closes[i]) / 3.0
            vol = volumes[i] if volumes[i] > 0.0 else 1.0
            sum_pv += typical * vol
            sum_v += vol
            if sum_v > 0:
                result.iloc[i] = sum_pv / sum_v

    return result
