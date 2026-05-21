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
