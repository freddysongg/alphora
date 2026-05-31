from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from typer.testing import CliRunner

from app.ml.cli import app
from app.ml.config import PathConfig
from app.ml.storage import write_parquet

runner = CliRunner()


def _write_raw(paths: PathConfig, ticker: str) -> None:
    n = 220
    idx = pd.date_range(
        "2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC", name="timestamp"
    )
    rng = np.random.default_rng(2)
    close = pd.Series(100.0 + rng.normal(0, 0.4, n).cumsum(), index=idx)
    frame = pd.DataFrame(
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
    write_parquet(frame, paths.raw_bars_path(ticker))


def test_build_dataset_from_cached_bars(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    _write_raw(paths, "AAPL")
    result = runner.invoke(
        app,
        [
            "build-dataset",
            "--ticker", "AAPL",
            "--from-date", "2025-01-02",
            "--to-date", "2025-01-03",
            "--run-id", "testrun",
            "--root", str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    dataset = pd.read_parquet(paths.dataset_dir("testrun") / "dataset.parquet")
    assert len(dataset) > 0
    assert (paths.dataset_dir("testrun") / "manifest.json").exists()
    assert (paths.dataset_dir("testrun") / "feature_spec.json").exists()
