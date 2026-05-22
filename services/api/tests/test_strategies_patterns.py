from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies._patterns import (
    FvgZone,
    find_recent_fvg,
    find_swing_high_low,
    pivot_low,
)


def _bars_from_ohlc(ohlc: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [base + timedelta(minutes=i) for i in range(len(ohlc))]
    return pd.DataFrame(
        {
            "open":   [o for o, _, _, _ in ohlc],
            "high":   [h for _, h, _, _ in ohlc],
            "low":    [low for _, _, low, _ in ohlc],
            "close":  [c for _, _, _, c in ohlc],
            "volume": [1000.0] * len(ohlc),
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_find_recent_fvg_returns_none_when_no_gaps() -> None:
    bars = _bars_from_ohlc([(100.0, 100.5, 99.5, 100.0)] * 10)
    result = find_recent_fvg(bars, end_idx=9, lookback=10)
    assert result.bull is None
    assert result.bear is None


def test_find_recent_fvg_detects_bullish_gap() -> None:
    ohlc = [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 101.0, 99.8, 100.5),
        (100.5, 101.5, 100.0, 101.0),
        (102.5, 103.0, 102.0, 102.8),
        (101.6, 102.5, 101.4, 102.2),
        (101.6, 102.5, 101.4, 102.2),
    ]
    bars = _bars_from_ohlc(ohlc)
    result = find_recent_fvg(bars, end_idx=5, lookback=10)
    assert result.bull is not None
    assert result.bull.high == 102.0
    assert result.bull.low == 101.0
    assert result.bull.bar_idx == 3


def test_find_recent_fvg_detects_bearish_gap() -> None:
    ohlc = [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.0, 99.5),
        (99.5, 99.5, 98.5, 99.0),
        (97.0, 97.5, 96.5, 97.0),
        (97.0, 97.5, 96.8, 97.2),
        (98.6, 98.7, 98.6, 98.7),
    ]
    bars = _bars_from_ohlc(ohlc)
    result = find_recent_fvg(bars, end_idx=6, lookback=10)
    assert result.bear is not None
    assert result.bear.high == 99.0
    assert result.bear.low == 97.5
    assert result.bear.bar_idx == 3


def test_find_recent_fvg_skips_filled_zones() -> None:
    ohlc = [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 101.0, 99.8, 100.5),
        (100.5, 101.5, 100.0, 101.0),
        (102.5, 103.0, 102.0, 102.8),
        (101.5, 102.0, 100.5, 101.0),
        (101.0, 101.5, 100.5, 101.0),
    ]
    bars = _bars_from_ohlc(ohlc)
    result = find_recent_fvg(bars, end_idx=5, lookback=10)
    assert result.bull is None


def test_find_swing_high_low_returns_window_extremes() -> None:
    bars = _bars_from_ohlc(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 101.0, 99.8, 100.5),
            (100.5, 102.0, 100.0, 101.5),
            (101.0, 101.5, 99.0, 100.5),
            (100.5, 100.8, 100.2, 100.5),
        ]
    )
    high, low = find_swing_high_low(bars, start_idx=0, end_idx=5)
    assert high == 102.0
    assert low == 99.0


def test_pivot_low_returns_most_recent_confirmed_pivot() -> None:
    bars = _bars_from_ohlc(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 99.3, 100.0),
            (100.0, 100.5, 99.0, 100.0),
            (100.0, 100.5, 99.3, 100.0),
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 99.6, 100.0),
            (100.0, 100.5, 99.7, 100.0),
        ]
    )
    result = pivot_low(bars, end_idx=6, lookback=10, left=2, right=2)
    assert result == 99.0


def test_pivot_low_returns_none_when_no_pivot_found() -> None:
    bars = _bars_from_ohlc([(100.0, 100.5, 99.5, 100.0)] * 5)
    result = pivot_low(bars, end_idx=4, lookback=10, left=2, right=2)
    assert result is None
