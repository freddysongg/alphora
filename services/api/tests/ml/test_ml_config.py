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
