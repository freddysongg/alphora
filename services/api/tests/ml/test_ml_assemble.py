from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.assemble import build_ticker_dataset, feature_columns
from app.ml.config import EtlConfig, FeatureConfig


def _bars(n: int) -> pd.DataFrame:
    idx = pd.date_range(
        "2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC", name="timestamp"
    )
    rng = np.random.default_rng(1)
    close = pd.Series(100.0 + rng.normal(0, 0.4, n).cumsum(), index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.7).to_numpy(),
            "low": (close - 0.7).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_build_ticker_dataset_has_label_and_features_no_nan() -> None:
    bars = _bars(200)
    frame = build_ticker_dataset("AAPL", bars, EtlConfig(
        tickers=("AAPL",), from_date=bars.index[0].date(), to_date=bars.index[-1].date()
    ))
    assert "ticker" in frame.columns
    assert (frame["ticker"] == "AAPL").all()
    assert "barrier_label" in frame.columns
    assert frame["barrier_label"].notna().all()
    for col in feature_columns(FeatureConfig()):
        assert frame[col].notna().all()


def test_build_ticker_dataset_is_deterministic() -> None:
    bars = _bars(200)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    a = build_ticker_dataset("AAPL", bars, cfg)
    b = build_ticker_dataset("AAPL", bars, cfg)
    pd.testing.assert_frame_equal(a, b)


def test_feature_columns_excludes_label_and_meta() -> None:
    cols = feature_columns(FeatureConfig())
    for forbidden in ("barrier_label", "touch_type", "label_return", "ticker",
                      "label_end_ts", "atr_at_entry", "is_rth"):
        assert forbidden not in cols
