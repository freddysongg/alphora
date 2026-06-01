from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig, PathConfig
from app.ml.storage import read_parquet

_NS_PER_DAY = 86_400_000_000_000

_INSIDER_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "change": "int64"}
_NEWS_SCHEMA = {"published_ts": "datetime64[ns, UTC]"}
_RECOMMENDATION_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "net_score": "float64"}
_FRED_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "value": "float64"}


@dataclass(frozen=True)
class ContextBundle:
    insider: pd.DataFrame
    news: pd.DataFrame
    recommendation: pd.DataFrame
    fred: dict[str, pd.DataFrame] = field(default_factory=dict)


def context_feature_columns(config: ContextConfig) -> list[str]:
    """Ordered context feature column names (must match build_context_features)."""
    cols = [f"insider_net_{config.insider_net_window_days}d", "insider_days_since"]
    cols += [f"news_count_{window}d" for window in config.news_count_windows_days]
    cols += ["rec_net_score"]
    for series_id in config.fred_series:
        cols += [f"fred_{series_id}", f"fred_{series_id}_chg"]
    return cols


def context_normalize_columns(config: ContextConfig) -> list[str]:
    """Context columns that get causal per-ticker z-scoring (scale-bearing ones).

    Recency (bounded by a cap), recommendation net-score (bounded in [-1, 1]), and
    FRED first-differences are left raw; counts, signed insider flow, and FRED
    levels vary by scale and are normalized.
    """
    cols = [f"insider_net_{config.insider_net_window_days}d"]
    cols += [f"news_count_{window}d" for window in config.news_count_windows_days]
    cols += [f"fred_{series_id}" for series_id in config.fred_series]
    return cols


def _insider_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    frame = bundle.insider.sort_values("available_ts")
    if frame.empty:
        event_ns = np.empty(0, dtype="int64")
        change = np.empty(0, dtype="float64")
    else:
        event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
        change = frame["change"].to_numpy(dtype="float64")

    window_ns = config.insider_net_window_days * _NS_PER_DAY
    prefix = np.concatenate([[0.0], np.cumsum(change)])
    upper = np.searchsorted(event_ns, bar_ns, side="right")
    lower = np.searchsorted(event_ns, bar_ns - window_ns, side="right")
    net = prefix[upper] - prefix[lower]

    last = upper - 1
    recency = np.full(len(bar_index), config.insider_recency_cap_days, dtype="float64")
    has_prior = last >= 0
    recency[has_prior] = np.minimum(
        (bar_ns[has_prior] - event_ns[last[has_prior]]) / _NS_PER_DAY,
        config.insider_recency_cap_days,
    )
    return pd.DataFrame(
        {
            f"insider_net_{config.insider_net_window_days}d": net,
            "insider_days_since": recency,
        },
        index=bar_index,
    )


def _news_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    if bundle.news.empty:
        event_ns = np.array([], dtype="int64")
    else:
        event_ns = np.sort(pd.DatetimeIndex(bundle.news["published_ts"]).asi8)
    upper = np.searchsorted(event_ns, bar_ns, side="right")
    data: dict[str, object] = {}
    for window in config.news_count_windows_days:
        lower = np.searchsorted(event_ns, bar_ns - window * _NS_PER_DAY, side="right")
        data[f"news_count_{window}d"] = (upper - lower).astype("float64")
    return pd.DataFrame(data, index=bar_index)


def _recommendation_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    out = np.zeros(len(bar_index), dtype="float64")
    frame = bundle.recommendation.sort_values("available_ts")
    if not frame.empty:
        event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
        score = frame["net_score"].to_numpy(dtype="float64")
        last = np.searchsorted(event_ns, bar_ns, side="right") - 1
        has_prior = last >= 0
        out[has_prior] = score[last[has_prior]]
    return pd.DataFrame({"rec_net_score": out}, index=bar_index)


def _fred_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    data: dict[str, object] = {}
    for series_id in config.fred_series:
        level = np.full(len(bar_index), np.nan, dtype="float64")
        change = np.full(len(bar_index), np.nan, dtype="float64")
        frame = bundle.fred.get(series_id)
        if frame is not None and not frame.empty:
            frame = frame.sort_values("available_ts")
            event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
            value = frame["value"].to_numpy(dtype="float64")
            last = np.searchsorted(event_ns, bar_ns, side="right") - 1
            has_prior = last >= 0
            level[has_prior] = value[last[has_prior]]
            prev = last - 1
            has_prev = has_prior & (prev >= 0)
            change[has_prev] = value[last[has_prev]] - value[prev[has_prev]]
            change[has_prior & (prev < 0)] = 0.0
        data[f"fred_{series_id}"] = level
        data[f"fred_{series_id}_chg"] = change
    return pd.DataFrame(data, index=bar_index)


def build_context_features(
    bar_index: pd.DatetimeIndex, bundle: ContextBundle, config: ContextConfig
) -> pd.DataFrame:
    """Context features aligned to `bar_index`, strictly causal (no future events)."""
    parts = [
        _insider_features(bundle, bar_index, config),
        _news_features(bundle, bar_index, config),
        _recommendation_features(bundle, bar_index, config),
        _fred_features(bundle, bar_index, config),
    ]
    out = pd.concat(parts, axis=1)
    return out[context_feature_columns(config)]


def _read_or_empty(path: Path, schema: dict[str, str]) -> pd.DataFrame:
    if path.exists():
        return read_parquet(path)
    return pd.DataFrame({name: pd.Series([], dtype=dtype) for name, dtype in schema.items()})


def load_context_bundle(
    ticker: str, config: ContextConfig, paths: PathConfig
) -> ContextBundle:
    """Load cached per-source context parquet into a ContextBundle for one ticker."""
    insider = _read_or_empty(paths.context_path("insider", ticker), _INSIDER_SCHEMA)
    news = _read_or_empty(paths.context_path("news", ticker), _NEWS_SCHEMA)
    recommendation = _read_or_empty(
        paths.context_path("recommendation", ticker), _RECOMMENDATION_SCHEMA
    )
    fred = {
        series_id: _read_or_empty(paths.context_path("fred", series_id), _FRED_SCHEMA)
        for series_id in config.fred_series
    }
    return ContextBundle(
        insider=insider, news=news, recommendation=recommendation, fred=fred
    )


__all__ = [
    "ContextBundle",
    "build_context_features",
    "context_feature_columns",
    "context_normalize_columns",
    "load_context_bundle",
]
