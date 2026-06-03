from __future__ import annotations

from collections.abc import Iterable

import pandas as pd  # type: ignore[import-untyped]


def causal_zscore(series: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    """Rolling z-score using only past-and-current values (no look-ahead).

    The rolling window ending at bar t includes t, all of whose inputs are
    known at t. A zero rolling std (constant window) yields 0.0, never inf.
    Positions with fewer than `min_periods` observations are NaN.
    """
    rolling = series.rolling(window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0)
    z = (series - mean) / std
    z = z.where(std != 0.0, 0.0)
    z = z.where(~mean.isna(), other=float("nan"))
    return z


def normalize_columns(
    frame: pd.DataFrame, columns: Iterable[str], *, window: int, min_periods: int
) -> pd.DataFrame:
    """Return a copy of `frame` with `columns` replaced by their causal z-scores."""
    out = frame.copy()
    for column in columns:
        out[column] = causal_zscore(
            frame[column].astype("float64"), window=window, min_periods=min_periods
        )
    return out


__all__ = ["causal_zscore", "normalize_columns"]
