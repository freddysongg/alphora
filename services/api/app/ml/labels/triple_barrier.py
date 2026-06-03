from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import BarrierConfig
from app.services.market_clock import to_et

_LABEL_COLUMNS = [
    "barrier_label",
    "touch_type",
    "label_return",
    "label_end_ts",
    "atr_at_entry",
]


def label_triple_barrier(
    bars: pd.DataFrame, atr_at_entry: pd.Series, config: BarrierConfig
) -> pd.DataFrame:
    """Session-aware, ATR-scaled triple-barrier labels aligned to `bars.index`.

    For each entry bar t with finite ATR, scan strictly-later bars within the
    same ET session, capped at t + horizon_bars. The first barrier touched
    wins: upper (close_t + pt_mult*ATR) -> label 1; lower
    (close_t - sl_mult*ATR) -> label 0. If no barrier is touched but the full
    horizon_bars window was observable within the session, the vertical barrier
    applies -> label 0. A single bar straddling both barriers is resolved by
    `config.ambiguous_bar_resolution`. Rows whose ATR is NaN, or whose full
    horizon cannot be observed within the same ET session (the last
    horizon_bars bars of each session, or a window truncated by end of data),
    are left unlabeled (NaN) and dropped during assembly.
    """
    closes = bars["close"].to_numpy(dtype="float64")
    highs = bars["high"].to_numpy(dtype="float64")
    lows = bars["low"].to_numpy(dtype="float64")
    atr_values = atr_at_entry.to_numpy(dtype="float64")
    session_days = [to_et(ts).day for ts in bars.index]
    n = len(bars)

    labels: list[float] = [float("nan")] * n
    touch_types: list[object] = [None] * n
    label_returns: list[float] = [float("nan")] * n
    label_end: list[object] = [None] * n

    for i in range(n):
        atr_i = atr_values[i]
        if not np.isfinite(atr_i) or atr_i <= 0.0:
            continue
        upper = closes[i] + config.pt_mult * atr_i
        lower = closes[i] - config.sl_mult * atr_i
        full_horizon_end = i + config.horizon_bars
        last_j = min(full_horizon_end, n - 1)
        session_truncated = False
        resolved = False
        for j in range(i + 1, last_j + 1):
            if session_days[j] != session_days[i]:
                last_j = j - 1
                session_truncated = True
                break
            hit_upper = highs[j] >= upper
            hit_lower = lows[j] <= lower
            if hit_upper and hit_lower:
                if config.ambiguous_bar_resolution == "lower_first":
                    labels[i], touch_types[i] = 0.0, "lower"
                else:
                    labels[i], touch_types[i] = 1.0, "upper"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
            if hit_upper:
                labels[i], touch_types[i] = 1.0, "upper"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
            if hit_lower:
                labels[i], touch_types[i] = 0.0, "lower"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
        if resolved:
            continue
        if not session_truncated and last_j == full_horizon_end:
            labels[i], touch_types[i] = 0.0, "vertical"
            label_returns[i] = closes[last_j] / closes[i] - 1.0
            label_end[i] = bars.index[last_j]

    out = pd.DataFrame(index=bars.index)
    out["barrier_label"] = labels
    out["touch_type"] = touch_types
    out["label_return"] = label_returns
    out["label_end_ts"] = label_end
    out["atr_at_entry"] = atr_values
    return out[_LABEL_COLUMNS]


__all__ = ["label_triple_barrier"]
