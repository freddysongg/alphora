from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig


def build_price_features(bars: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Causal price/volume features aligned to `bars.index`.

    Every value at bar t uses only data at or before t. Warmup positions are
    NaN and are dropped later during assembly.
    """
    close = bars["close"].astype("float64")
    out = pd.DataFrame(index=bars.index)

    log_close = np.log(close)
    for window in config.return_windows:
        out[f"ret_{window}"] = log_close.diff(window)

    out["hl_range"] = (bars["high"] - bars["low"]) / close
    out["co_change"] = (close - bars["open"]) / bars["open"]
    out["gap_prev_close"] = close / close.shift(1) - 1.0

    volume = bars["volume"].astype("float64")
    rolling_volume = volume.rolling(
        config.relative_volume_window, min_periods=config.relative_volume_window
    ).mean()
    out["rel_volume"] = volume / rolling_volume

    one_bar_ret = log_close.diff(1)
    out["realized_vol"] = one_bar_ret.rolling(
        config.realized_vol_window, min_periods=config.realized_vol_window
    ).std()

    return out


__all__ = ["build_price_features"]
