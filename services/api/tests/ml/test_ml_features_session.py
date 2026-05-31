from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.ml.features.session import build_session_features


def test_session_features_minutes_since_open() -> None:
    idx = pd.DatetimeIndex(
        ["2025-01-02T14:30:00Z", "2025-01-02T15:00:00Z", "2025-01-02T20:55:00Z"],
        tz="UTC",
    )
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=idx)
    feats = build_session_features(frame)
    assert feats["minutes_since_open"].tolist() == [0, 30, 385]
    assert feats["is_first_30min"].tolist() == [True, True, False]
    assert feats["is_last_30min"].tolist() == [False, False, True]


def test_session_features_day_of_week() -> None:
    idx = pd.DatetimeIndex(["2025-01-02T15:00:00Z"], tz="UTC")  # Thursday
    frame = pd.DataFrame({"close": [1.0]}, index=idx)
    feats = build_session_features(frame)
    assert feats["day_of_week"].iloc[0] == 3


def test_session_features_align_to_index() -> None:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=10, freq="5min", tz="UTC")
    frame = pd.DataFrame({"close": range(10)}, index=idx)
    feats = build_session_features(frame)
    assert feats.index.equals(frame.index)
