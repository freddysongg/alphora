from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig, PathConfig
from app.ml.features.context_join import (
    ContextBundle,
    build_context_features,
    context_feature_columns,
    context_normalize_columns,
    load_context_bundle,
)
from app.ml.storage import write_parquet


def _empty_insider() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
            "change": pd.Series([], dtype="int64"),
        }
    )


def _empty_news() -> pd.DataFrame:
    return pd.DataFrame({"published_ts": pd.Series([], dtype="datetime64[ns, UTC]")})


def _empty_rec() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
            "net_score": pd.Series([], dtype="float64"),
        }
    )


def test_context_feature_columns_order() -> None:
    cols = context_feature_columns(ContextConfig())
    assert cols == [
        "insider_net_30d",
        "insider_days_since",
        "news_count_1d",
        "news_count_5d",
        "news_count_20d",
        "rec_net_score",
        "fred_DGS10",
        "fred_DGS10_chg",
        "fred_VIXCLS",
        "fred_VIXCLS_chg",
        "fred_T10Y2Y",
        "fred_T10Y2Y_chg",
    ]


def test_context_normalize_columns_subset() -> None:
    cols = context_normalize_columns(ContextConfig())
    assert cols == [
        "insider_net_30d",
        "news_count_1d",
        "news_count_5d",
        "news_count_20d",
        "fred_DGS10",
        "fred_VIXCLS",
        "fred_T10Y2Y",
    ]


def test_event_after_bar_never_appears() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-10T14:30:00Z"], tz="UTC")
    insider = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(["2025-03-11T00:00:00Z"], utc=True),
            "change": [-1000],
        }
    )
    news = pd.DataFrame(
        {"published_ts": pd.to_datetime(["2025-03-11T10:00:00Z"], utc=True)}
    )
    rec = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(["2025-03-12T00:00:00Z"], utc=True),
            "net_score": [0.9],
        }
    )
    fred = {
        "DGS10": pd.DataFrame(
            {
                "available_ts": pd.to_datetime(["2025-03-12T00:00:00Z"], utc=True),
                "value": [4.5],
            }
        )
    }
    bundle = ContextBundle(insider=insider, news=news, recommendation=rec, fred=fred)
    cfg = ContextConfig(fred_series=("DGS10",))
    feats = build_context_features(bar_index, bundle, cfg)
    assert feats.loc[bar_index[0], "insider_net_30d"] == 0.0
    assert feats.loc[bar_index[0], "insider_days_since"] == cfg.insider_recency_cap_days
    assert feats.loc[bar_index[0], "news_count_1d"] == 0.0
    assert feats.loc[bar_index[0], "rec_net_score"] == 0.0
    assert pd.isna(feats.loc[bar_index[0], "fred_DGS10"])


def test_news_counts_trailing_windows() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-10T14:30:00Z"], tz="UTC")
    news = pd.DataFrame(
        {
            "published_ts": pd.to_datetime(
                ["2025-03-10T10:00:00Z", "2025-03-09T10:00:00Z", "2025-03-01T10:00:00Z"],
                utc=True,
            )
        }
    )
    bundle = ContextBundle(
        insider=_empty_insider(), news=news, recommendation=_empty_rec(), fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "news_count_1d"] == 1.0
    assert feats.loc[bar_index[0], "news_count_5d"] == 2.0
    assert feats.loc[bar_index[0], "news_count_20d"] == 3.0


def test_insider_net_and_recency() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    insider = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(
                ["2025-03-10T00:00:00Z", "2025-03-18T00:00:00Z"], utc=True
            ),
            "change": [1000, -400],
        }
    )
    bundle = ContextBundle(
        insider=insider, news=_empty_news(), recommendation=_empty_rec(), fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "insider_net_30d"] == 600.0
    assert abs(feats.loc[bar_index[0], "insider_days_since"] - (2 + 14.5 / 24)) < 1e-6


def test_recommendation_forward_fill() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    rec = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(
                ["2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z"], utc=True
            ),
            "net_score": [0.2, 0.5],
        }
    )
    bundle = ContextBundle(
        insider=_empty_insider(), news=_empty_news(), recommendation=rec, fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "rec_net_score"] == 0.5


def test_fred_level_and_change_forward_fill() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    fred = {
        "DGS10": pd.DataFrame(
            {
                "available_ts": pd.to_datetime(
                    ["2025-03-18T00:00:00Z", "2025-03-19T00:00:00Z"], utc=True
                ),
                "value": [4.20, 4.30],
            }
        )
    }
    bundle = ContextBundle(
        insider=_empty_insider(), news=_empty_news(), recommendation=_empty_rec(),
        fred=fred,
    )
    feats = build_context_features(bar_index, bundle, ContextConfig(fred_series=("DGS10",)))
    assert abs(feats.loc[bar_index[0], "fred_DGS10"] - 4.30) < 1e-9
    assert abs(feats.loc[bar_index[0], "fred_DGS10_chg"] - 0.10) < 1e-9


def test_load_context_bundle_roundtrip(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    write_parquet(
        pd.DataFrame(
            {
                "available_ts": pd.to_datetime(["2025-03-10T00:00:00Z"], utc=True),
                "change": [100],
            }
        ),
        paths.context_path("insider", "AAPL"),
    )
    bundle = load_context_bundle("AAPL", ContextConfig(fred_series=()), paths)
    assert bundle.insider["change"].tolist() == [100]
    assert list(bundle.news.columns) == ["published_ts"]
    assert bundle.news.empty
    assert bundle.fred == {}
