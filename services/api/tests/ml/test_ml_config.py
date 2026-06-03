from __future__ import annotations

from datetime import date
from pathlib import Path

from app.ml.config import BarrierConfig, EtlConfig, FeatureConfig, PathConfig


def test_barrier_config_defaults() -> None:
    cfg = BarrierConfig()
    assert cfg.pt_mult == 2.0
    assert cfg.sl_mult == 1.0
    assert cfg.horizon_bars == 12
    assert cfg.atr_period == 14
    assert cfg.ambiguous_bar_resolution == "lower_first"


def test_feature_config_defaults() -> None:
    cfg = FeatureConfig()
    assert cfg.return_windows == (1, 3, 6, 12)
    assert cfg.normalize_window == 100
    assert cfg.rsi_period == 14


def test_paths_are_rooted_under_data_ml(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    assert paths.raw_bars_dir == tmp_path / "raw_bars" / "5min"
    assert paths.dataset_dir("run1") == tmp_path / "datasets" / "run1"


def test_etl_config_composes() -> None:
    cfg = EtlConfig(
        tickers=("AAPL", "SPY"),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
    )
    assert cfg.tickers == ("AAPL", "SPY")
    assert cfg.barrier.pt_mult == 2.0
    assert cfg.rth_only is True


def test_context_config_defaults() -> None:
    from app.ml.config import ContextConfig

    cfg = ContextConfig()
    assert cfg.insider_net_window_days == 30
    assert cfg.insider_recency_cap_days == 252.0
    assert cfg.insider_lag_days == 1
    assert cfg.news_count_windows_days == (1, 5, 20)
    assert cfg.recommendation_lag_days == 0
    assert cfg.fred_series == ("DGS10", "VIXCLS", "T10Y2Y")
    assert cfg.fred_lag_days == 1
    assert cfg.fred_history_days == 365
    assert cfg.normalize_window == 100
    assert cfg.normalize_min_periods == 30


def test_etl_config_context_defaults_to_none() -> None:
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
    )
    assert cfg.context is None


def test_path_config_context_path(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    assert paths.context_dir == tmp_path / "context"
    assert paths.context_path("insider", "AAPL") == (
        tmp_path / "context" / "insider" / "AAPL.parquet"
    )
    assert paths.context_path("fred", "DGS10") == (
        tmp_path / "context" / "fred" / "DGS10.parquet"
    )
