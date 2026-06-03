from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig
from app.ml.features.price import build_price_features


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    close = pd.Series(np.linspace(100.0, 110.0, n), index=idx)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]).to_numpy(),
            "high": (close + 0.5).to_numpy(),
            "low": (close - 0.5).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_price_features_have_expected_columns() -> None:
    feats = build_price_features(_frame(60), FeatureConfig())
    for window in (1, 3, 6, 12):
        assert f"ret_{window}" in feats.columns
    assert "hl_range" in feats.columns
    assert "gap_prev_close" in feats.columns
    assert "rel_volume" in feats.columns
    assert "realized_vol" in feats.columns


def test_log_return_one_bar_matches_manual() -> None:
    feats = build_price_features(_frame(10), FeatureConfig())
    frame = _frame(10)
    expected = np.log(frame["close"].iloc[5] / frame["close"].iloc[4])
    assert abs(feats["ret_1"].iloc[5] - expected) < 1e-9


def test_price_features_index_aligns_with_input() -> None:
    frame = _frame(30)
    feats = build_price_features(frame, FeatureConfig())
    assert feats.index.equals(frame.index)
