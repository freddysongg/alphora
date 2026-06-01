from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.ml.assemble import build_ticker_dataset, feature_columns
from app.ml.config import ContextConfig, EtlConfig, FeatureConfig
from app.ml.features.context_join import ContextBundle, context_feature_columns


def _bars(n: int) -> pd.DataFrame:
    idx = pd.date_range(
        "2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC", name="timestamp"
    )
    rng = np.random.default_rng(1)
    close = pd.Series(100.0 + rng.normal(0, 0.4, n).cumsum(), index=idx)
    return pd.DataFrame(
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


def test_build_ticker_dataset_has_label_and_features_no_nan() -> None:
    bars = _bars(200)
    frame = build_ticker_dataset("AAPL", bars, EtlConfig(
        tickers=("AAPL",), from_date=bars.index[0].date(), to_date=bars.index[-1].date()
    ))
    assert "ticker" in frame.columns
    assert (frame["ticker"] == "AAPL").all()
    assert "barrier_label" in frame.columns
    assert frame["barrier_label"].notna().all()
    for col in feature_columns(FeatureConfig()):
        assert frame[col].notna().all()


def test_build_ticker_dataset_is_deterministic() -> None:
    bars = _bars(200)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    a = build_ticker_dataset("AAPL", bars, cfg)
    b = build_ticker_dataset("AAPL", bars, cfg)
    pd.testing.assert_frame_equal(a, b)


def test_feature_columns_excludes_label_and_meta() -> None:
    cols = feature_columns(FeatureConfig())
    for forbidden in ("barrier_label", "touch_type", "label_return", "ticker",
                      "label_end_ts", "atr_at_entry", "is_rth"):
        assert forbidden not in cols


def _context_bundle(bars: pd.DataFrame) -> ContextBundle:
    start = bars.index[0]
    insider = pd.DataFrame(
        {
            "available_ts": [start - pd.Timedelta(days=2)],
            "change": [1000],
        }
    )
    news = pd.DataFrame(
        {"published_ts": [start - pd.Timedelta(hours=3), start + pd.Timedelta(hours=1)]}
    )
    recommendation = pd.DataFrame(
        {"available_ts": [start - pd.Timedelta(days=5)], "net_score": [0.4]}
    )
    fred = {
        series_id: pd.DataFrame(
            {
                "available_ts": [
                    start - pd.Timedelta(days=3),
                    start - pd.Timedelta(days=2),
                ],
                "value": [4.2, 4.3],
            }
        )
        for series_id in ("DGS10", "VIXCLS", "T10Y2Y")
    }
    return ContextBundle(
        insider=insider, news=news, recommendation=recommendation, fred=fred
    )


def test_build_ticker_dataset_appends_context_columns() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    frame = build_ticker_dataset("AAPL", bars, cfg, context=_context_bundle(bars))
    for col in context_feature_columns(ContextConfig()):
        assert col in frame.columns
        assert frame[col].notna().all()
    assert frame["barrier_label"].notna().all()


def test_build_ticker_dataset_context_is_deterministic() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    bundle = _context_bundle(bars)
    a = build_ticker_dataset("AAPL", bars, cfg, context=bundle)
    b = build_ticker_dataset("AAPL", bars, cfg, context=bundle)
    pd.testing.assert_frame_equal(a, b)


def test_build_ticker_dataset_without_context_has_no_context_columns() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
    )
    frame = build_ticker_dataset("AAPL", bars, cfg)
    for col in context_feature_columns(ContextConfig()):
        assert col not in frame.columns


def test_build_ticker_dataset_context_config_without_bundle_raises() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    with pytest.raises(ValueError, match="context"):
        build_ticker_dataset("AAPL", bars, cfg)
