from __future__ import annotations

import math

import pandas as pd
import pytest

from app.indicators import ema


def _close_series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2026-06-15 13:30:00+00:00", periods=len(values), freq="1min")
    return pd.Series(values, index=idx, name="close", dtype="float64")


def test_ema_returns_series_of_same_length_as_input() -> None:
    closes = _close_series([100.0] * 20)
    out = ema(closes, period=5)
    assert isinstance(out, pd.Series)
    assert len(out) == 20


def test_ema_warmup_region_is_nan() -> None:
    closes = _close_series([100.0 + i for i in range(20)])
    out = ema(closes, period=5)
    assert all(math.isnan(v) for v in out.iloc[:4])
    assert not math.isnan(out.iloc[4])


def test_ema_of_constant_series_after_warmup_equals_constant() -> None:
    closes = _close_series([100.0] * 30)
    out = ema(closes, period=5)
    tail = out.iloc[4:]
    assert all(abs(v - 100.0) < 1e-9 for v in tail)


def test_ema_raises_when_series_too_short() -> None:
    closes = _close_series([100.0, 101.0])
    with pytest.raises(ValueError, match="ema"):
        ema(closes, period=10)


from app.indicators import macd  # noqa: E402


def test_macd_returns_three_aligned_series() -> None:
    closes = _close_series([100.0 + 0.1 * i for i in range(60)])
    macd_line, signal_line, hist = macd(closes, fast=12, slow=26, signal=9)
    assert isinstance(macd_line, pd.Series)
    assert isinstance(signal_line, pd.Series)
    assert isinstance(hist, pd.Series)
    assert len(macd_line) == 60
    assert len(signal_line) == 60
    assert len(hist) == 60


def test_macd_warmup_yields_nan_until_slow_period() -> None:
    closes = _close_series([100.0 + 0.1 * i for i in range(60)])
    macd_line, _, _ = macd(closes, fast=12, slow=26, signal=9)
    assert math.isnan(macd_line.iloc[24])
    assert not math.isnan(macd_line.iloc[25])


def test_macd_histogram_equals_macd_minus_signal_post_warmup() -> None:
    closes = _close_series([100.0 + 0.1 * i for i in range(60)])
    macd_line, signal_line, hist = macd(closes, fast=12, slow=26, signal=9)
    last = -1
    assert abs(hist.iloc[last] - (macd_line.iloc[last] - signal_line.iloc[last])) < 1e-9


from app.indicators import rsi  # noqa: E402


def test_rsi_returns_aligned_series_with_period_warmup() -> None:
    closes = _close_series([100.0 + i for i in range(30)])
    out = rsi(closes, period=14)
    assert isinstance(out, pd.Series)
    assert len(out) == 30
    assert all(math.isnan(v) for v in out.iloc[:14])
    assert not math.isnan(out.iloc[14])


def test_rsi_monotonic_uptrend_is_high() -> None:
    closes = _close_series([100.0 + i for i in range(30)])
    out = rsi(closes, period=14)
    assert out.iloc[-1] >= 99.0


def test_rsi_values_stay_within_bounds() -> None:
    closes = _close_series([100.0 + (i % 5) for i in range(40)])
    out = rsi(closes, period=14)
    valid = out.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()
