from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from app.indicators import atr
from app.ml.config import EtlConfig, FeatureConfig
from app.ml.features.normalize import normalize_columns
from app.ml.features.price import build_price_features
from app.ml.features.session import build_session_features
from app.ml.features.technical import build_technical_features
from app.ml.labels.triple_barrier import label_triple_barrier
from app.ml.storage import write_json, write_parquet

_META_COLUMNS = [
    "ticker",
    "barrier_label",
    "touch_type",
    "label_return",
    "label_end_ts",
    "atr_at_entry",
]

_NORMALIZE_COLUMNS = (
    "macd_line",
    "macd_signal",
    "macd_hist",
    "atr",
    "realized_vol",
    "hl_range",
)


def feature_columns(config: FeatureConfig) -> list[str]:
    """The ordered list of model-facing feature columns (no label/meta)."""
    cols: list[str] = [f"ret_{w}" for w in config.return_windows]
    cols += ["hl_range", "co_change", "gap_prev_close", "rel_volume", "realized_vol"]
    cols += [
        "rsi", "macd_line", "macd_signal", "macd_hist", "adx", "atr",
        "bb_pct", "ema_fast_ratio", "ema_slow_ratio",
    ]
    cols += ["minutes_since_open", "day_of_week", "is_first_30min", "is_last_30min"]
    return cols


def build_ticker_dataset(
    ticker: str, bars: pd.DataFrame, config: EtlConfig
) -> pd.DataFrame:
    """Build a labeled, feature-complete dataset for one ticker (RTH bars only)."""
    rth = bars[bars["is_rth"]] if config.rth_only else bars
    rth = rth.sort_index()

    price = build_price_features(rth, config.features)
    technical = build_technical_features(rth, config.features)
    session = build_session_features(rth)
    atr_series = atr(rth, period=config.barrier.atr_period)
    labels = label_triple_barrier(rth, atr_series, config.barrier)

    features = pd.concat([price, technical, session], axis=1)
    features = normalize_columns(
        features,
        _NORMALIZE_COLUMNS,
        window=config.features.normalize_window,
        min_periods=config.features.normalize_min_periods,
    )

    combined = pd.concat([features, labels], axis=1)
    combined.insert(0, "ticker", ticker)
    combined = combined[feature_columns(config.features) + _META_COLUMNS]

    feature_only = combined[feature_columns(config.features)]
    combined = combined[
        feature_only.notna().all(axis=1) & combined["barrier_label"].notna()
    ]
    combined = combined.reset_index().rename(columns={"timestamp": "entry_ts"})
    combined["session_date"] = combined["entry_ts"].dt.tz_convert(
        "America/New_York"
    ).dt.date.astype(str)
    return combined.sort_values(["ticker", "entry_ts"]).reset_index(drop=True)


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def assemble_dataset(
    run_id: str,
    per_ticker: dict[str, pd.DataFrame],
    config: EtlConfig,
) -> Path:
    """Concatenate per-ticker datasets, write dataset.parquet + manifest + spec."""
    frames = [frame for frame in per_ticker.values() if not frame.empty]
    dataset = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=feature_columns(config.features) + _META_COLUMNS)
    )
    out_dir = config.paths.dataset_dir(run_id)
    write_parquet(dataset, out_dir / "dataset.parquet")

    label_balance: dict[str, Any] = (
        dataset["barrier_label"].value_counts().to_dict() if not dataset.empty else {}
    )
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "git_sha": _git_sha(),
        "from_date": config.from_date,
        "to_date": config.to_date,
        "rth_only": config.rth_only,
        "barrier": vars(config.barrier),
        "tickers": list(per_ticker.keys()),
        "row_counts": {t: len(f) for t, f in per_ticker.items()},
        "total_rows": len(dataset),
        "label_balance": {str(k): int(v) for k, v in label_balance.items()},
    }
    write_json(manifest, out_dir / "manifest.json")

    spec: dict[str, Any] = {
        "features": feature_columns(config.features),
        "normalized": list(_NORMALIZE_COLUMNS),
        "label": "barrier_label",
    }
    write_json(spec, out_dir / "feature_spec.json")
    return out_dir


__all__ = [
    "assemble_dataset",
    "build_ticker_dataset",
    "feature_columns",
]
