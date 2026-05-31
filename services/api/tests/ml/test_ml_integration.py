from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.assemble import build_ticker_dataset, feature_columns
from app.ml.config import EtlConfig, FeatureConfig


def _bars(n: int, seed: int) -> pd.DataFrame:
    idx = pd.date_range(
        "2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC", name="timestamp"
    )
    rng = np.random.default_rng(seed)
    close = pd.Series(100.0 + rng.normal(0, 0.5, n).cumsum(), index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.8).to_numpy(),
            "low": (close - 0.8).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_label_end_is_strictly_after_entry() -> None:
    bars = _bars(220, 3)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    ds = build_ticker_dataset("AAPL", bars, cfg)
    labeled = ds[ds["label_end_ts"].notna()]
    assert (labeled["label_end_ts"] > labeled["entry_ts"]).all()


def test_modifying_future_bars_never_changes_past_features() -> None:
    bars = _bars(220, 4)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    base = build_ticker_dataset("AAPL", bars, cfg)

    tampered = bars.copy()
    tampered.iloc[180:, tampered.columns.get_loc("close")] *= 1.5
    tampered.iloc[180:, tampered.columns.get_loc("high")] *= 1.5
    after = build_ticker_dataset("AAPL", tampered, cfg)

    cutoff = base["entry_ts"].iloc[100]
    cols = feature_columns(FeatureConfig())
    base_head = base[base["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    after_head = after[after["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_head, after_head)
