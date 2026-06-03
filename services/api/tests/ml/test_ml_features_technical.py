from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig
from app.ml.features.technical import build_technical_features


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(0)
    steps = rng.normal(0, 0.3, n).cumsum()
    close = pd.Series(100.0 + steps, index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.6).to_numpy(),
            "low": (close - 0.6).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_technical_features_have_expected_columns() -> None:
    feats = build_technical_features(_frame(120), FeatureConfig())
    for col in (
        "rsi",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "adx",
        "atr",
        "bb_pct",
        "ema_fast_ratio",
        "ema_slow_ratio",
    ):
        assert col in feats.columns


def test_technical_features_align_to_input_index() -> None:
    frame = _frame(120)
    feats = build_technical_features(frame, FeatureConfig())
    assert feats.index.equals(frame.index)


def test_atr_column_matches_indicator_wrapper() -> None:
    from app.indicators import atr

    frame = _frame(120)
    feats = build_technical_features(frame, FeatureConfig())
    expected = atr(frame, period=14)
    pd.testing.assert_series_equal(
        feats["atr"], expected, check_names=False
    )
