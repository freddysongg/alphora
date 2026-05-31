from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.features.normalize import causal_zscore


def test_zscore_is_nan_before_min_periods() -> None:
    s = pd.Series(np.arange(100, dtype="float64"))
    z = causal_zscore(s, window=20, min_periods=10)
    assert z.iloc[:9].isna().all()
    assert not np.isnan(z.iloc[50])


def test_zscore_uses_only_past_and_current() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 100.0, 5.0, 6.0])
    z = causal_zscore(s, window=10, min_periods=2)
    later = pd.Series([1.0, 2.0, 3.0, 100.0, 999.0, 6.0])
    z_later = causal_zscore(later, window=10, min_periods=2)
    assert z.iloc[3] == z_later.iloc[3]


def test_zscore_constant_window_yields_zero_not_inf() -> None:
    s = pd.Series([5.0] * 30)
    z = causal_zscore(s, window=10, min_periods=5)
    assert np.isfinite(z.iloc[-1])
    assert z.iloc[-1] == 0.0
