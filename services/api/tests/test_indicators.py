from __future__ import annotations

import math

import pandas as pd  # type: ignore[import-untyped]
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


from app.indicators import adx  # noqa: E402


def _ohlcv_frame(closes: list[float], *, range_amp: float = 0.5) -> pd.DataFrame:
    idx = pd.date_range("2026-06-15 13:30:00+00:00", periods=len(closes), freq="1min")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + range_amp for c in closes],
            "low": [c - range_amp for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def test_adx_returns_aligned_series_warmup_nan() -> None:
    bars = _ohlcv_frame([100.0 + 0.1 * i for i in range(60)])
    out = adx(bars, period=14)
    assert isinstance(out, pd.Series)
    assert len(out) == 60
    # ADX needs 2*period bars to start producing values
    assert math.isnan(out.iloc[27])
    assert not math.isnan(out.iloc[-1])


def test_adx_strong_uptrend_is_above_25() -> None:
    bars = _ohlcv_frame([100.0 + 1.0 * i for i in range(60)])
    out = adx(bars, period=14)
    assert out.iloc[-1] >= 25.0


def test_adx_flat_series_is_below_25() -> None:
    bars = _ohlcv_frame([100.0] * 60)
    out = adx(bars, period=14)
    valid = out.dropna()
    if len(valid) > 0:
        assert valid.iloc[-1] < 25.0


from app.indicators import atr  # noqa: E402


def test_atr_returns_aligned_series_warmup_nan() -> None:
    bars = _ohlcv_frame([100.0 + 0.1 * i for i in range(40)])
    out = atr(bars, period=14)
    assert isinstance(out, pd.Series)
    assert len(out) == 40
    assert math.isnan(out.iloc[13])
    assert not math.isnan(out.iloc[14])


def test_atr_is_positive_when_range_is_positive() -> None:
    bars = _ohlcv_frame([100.0 + 0.1 * i for i in range(40)], range_amp=0.5)
    out = atr(bars, period=14)
    valid = out.dropna()
    assert (valid > 0).all()


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


from app.indicators import bollinger  # noqa: E402


def test_bollinger_returns_three_named_series_aligned_to_close() -> None:
    closes = _close_series([100.0 + i * 0.1 for i in range(40)])
    middle, upper, lower = bollinger(closes, period=20, mult=2.0)
    assert len(middle) == len(closes) == 40
    assert len(upper) == 40
    assert len(lower) == 40
    for i in range(19):
        assert math.isnan(float(middle.iloc[i]))
    assert not math.isnan(float(middle.iloc[19]))


def test_bollinger_population_stddev_matches_source_bot() -> None:
    closes = _close_series([100.0 + i for i in range(20)])
    middle, upper, lower = bollinger(closes, period=20, mult=2.0)
    assert math.isclose(float(middle.iloc[19]), 109.5, abs_tol=1e-9)
    expected_std = math.sqrt(33.25)
    assert math.isclose(float(upper.iloc[19]), 109.5 + 2 * expected_std, abs_tol=1e-9)
    assert math.isclose(float(lower.iloc[19]), 109.5 - 2 * expected_std, abs_tol=1e-9)


def test_bollinger_with_period_2_and_constant_input_gives_zero_band_width() -> None:
    closes = _close_series([100.0, 100.0, 100.0])
    middle, upper, lower = bollinger(closes, period=2, mult=2.0)
    assert math.isclose(float(middle.iloc[2]), 100.0)
    assert math.isclose(float(upper.iloc[2]), 100.0)
    assert math.isclose(float(lower.iloc[2]), 100.0)
