from __future__ import annotations

from pathlib import Path

import httpx
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import pytest
import respx
from typer.testing import CliRunner

from app.config import get_settings
from app.ml.cli import app
from app.ml.config import ContextConfig, PathConfig
from app.ml.features.context_join import context_feature_columns
from app.ml.storage import read_parquet, write_parquet

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


def _write_context(paths: PathConfig, ticker: str) -> None:
    start = pd.Timestamp("2025-01-02T14:30:00Z")
    write_parquet(
        pd.DataFrame(
            {"available_ts": [start - pd.Timedelta(days=2)], "change": [1000]}
        ),
        paths.context_path("insider", ticker),
    )
    write_parquet(
        pd.DataFrame({"published_ts": [start - pd.Timedelta(hours=2)]}),
        paths.context_path("news", ticker),
    )
    write_parquet(
        pd.DataFrame(
            {"available_ts": [start - pd.Timedelta(days=5)], "net_score": [0.3]}
        ),
        paths.context_path("recommendation", ticker),
    )
    for series_id in ContextConfig().fred_series:
        write_parquet(
            pd.DataFrame(
                {
                    "available_ts": [
                        start - pd.Timedelta(days=3),
                        start - pd.Timedelta(days=2),
                    ],
                    "value": [4.2, 4.3],
                }
            ),
            paths.context_path("fred", series_id),
        )


def test_build_dataset_with_context_includes_context_columns(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    _write_raw(paths, "AAPL")
    _write_context(paths, "AAPL")
    result = runner.invoke(
        app,
        [
            "build-dataset",
            "--ticker", "AAPL",
            "--from-date", "2025-01-02",
            "--to-date", "2025-01-03",
            "--run-id", "ctxrun",
            "--root", str(tmp_path),
            "--with-context",
        ],
    )
    assert result.exit_code == 0, result.output
    dataset = read_parquet(paths.dataset_dir("ctxrun") / "dataset.parquet")
    for col in context_feature_columns(ContextConfig()):
        assert col in dataset.columns
    assert len(dataset) > 0


@respx.mock
def test_pull_context_writes_source_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test-key")
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    get_settings.cache_clear()

    respx.get("https://finnhub.io/api/v1/stock/insider-transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "data": [
                    {
                        "name": "Tim Cook", "share": 1000, "change": -500,
                        "filingDate": "2026-05-15", "transactionDate": "2026-05-13",
                        "transactionCode": "S",
                    }
                ],
            },
        )
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(
            200,
            json={
                "observation_start": "2025-05-01",
                "observation_end": "2026-05-20",
                "count": 1,
                "observations": [
                    {"date": "2026-05-01", "value": "4.25",
                     "realtime_start": "2026-05-02", "realtime_end": "2026-12-31"}
                ],
            },
        )
    )

    paths = PathConfig(root=tmp_path)
    result = runner.invoke(
        app,
        [
            "pull-context",
            "--ticker", "AAPL",
            "--from-date", "2026-05-01",
            "--to-date", "2026-05-20",
            "--root", str(tmp_path),
            "--fred-series", "DGS10",
        ],
    )
    assert result.exit_code == 0, result.output
    assert paths.context_path("insider", "AAPL").exists()
    assert paths.context_path("news", "AAPL").exists()
    assert paths.context_path("recommendation", "AAPL").exists()
    assert paths.context_path("fred", "DGS10").exists()
