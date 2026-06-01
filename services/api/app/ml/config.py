from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

AmbiguousResolution = Literal["lower_first", "upper_first"]

_DEFAULT_ROOT = Path("data/ml")


@dataclass(frozen=True)
class BarrierConfig:
    pt_mult: float = 2.0
    sl_mult: float = 1.0
    horizon_bars: int = 12
    atr_period: int = 14
    ambiguous_bar_resolution: AmbiguousResolution = "lower_first"


@dataclass(frozen=True)
class FeatureConfig:
    return_windows: tuple[int, ...] = (1, 3, 6, 12)
    rsi_period: int = 14
    adx_period: int = 14
    atr_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 20
    bollinger_period: int = 20
    bollinger_mult: float = 2.0
    realized_vol_window: int = 12
    relative_volume_window: int = 20
    normalize_window: int = 100
    normalize_min_periods: int = 30


@dataclass(frozen=True)
class ContextConfig:
    insider_net_window_days: int = 30
    insider_recency_cap_days: float = 252.0
    insider_lag_days: int = 1
    news_count_windows_days: tuple[int, ...] = (1, 5, 20)
    recommendation_lag_days: int = 0
    fred_series: tuple[str, ...] = ("DGS10", "VIXCLS", "T10Y2Y")
    fred_lag_days: int = 1
    fred_history_days: int = 365
    normalize_window: int = 100
    normalize_min_periods: int = 30


@dataclass(frozen=True)
class PathConfig:
    root: Path = _DEFAULT_ROOT

    @property
    def raw_bars_dir(self) -> Path:
        return self.root / "raw_bars" / "5min"

    def raw_bars_path(self, ticker: str) -> Path:
        return self.raw_bars_dir / f"{ticker}.parquet"

    @property
    def datasets_root(self) -> Path:
        return self.root / "datasets"

    def dataset_dir(self, run_id: str) -> Path:
        return self.datasets_root / run_id

    @property
    def context_dir(self) -> Path:
        return self.root / "context"

    def context_path(self, source: str, key: str) -> Path:
        return self.context_dir / source / f"{key}.parquet"


@dataclass(frozen=True)
class EtlConfig:
    tickers: tuple[str, ...]
    from_date: date
    to_date: date
    rth_only: bool = True
    barrier: BarrierConfig = field(default_factory=BarrierConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    context: ContextConfig | None = None


__all__ = [
    "AmbiguousResolution",
    "BarrierConfig",
    "ContextConfig",
    "EtlConfig",
    "FeatureConfig",
    "PathConfig",
]
