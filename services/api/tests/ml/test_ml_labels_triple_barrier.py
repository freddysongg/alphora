from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import BarrierConfig
from app.ml.labels.triple_barrier import label_triple_barrier


def _session_frame(closes: list[float], highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_upper_barrier_hit_first_labels_1() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    highs[5] = 105.0  # large up-spike within horizon
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 1
    assert labels.loc[frame.index[0], "touch_type"] == "upper"


def test_lower_barrier_hit_first_labels_0() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    lows[3] = 98.0  # down-spike crosses -1*ATR before any up-move
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "lower"


def test_no_touch_within_horizon_is_vertical_zero() -> None:
    closes = [100.0] * 20
    highs = [100.2] * 20
    lows = [99.8] * 20
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=5)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "vertical"


def test_session_tail_rows_are_unlabeled() -> None:
    closes = [100.0] * 6
    highs = [100.2] * 6
    lows = [99.8] * 6
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    # no entry has a full 12-bar in-session horizon -> every row is unlabeled
    assert labels["barrier_label"].isna().all()


def test_only_full_horizon_entries_are_labeled() -> None:
    # single session, flat prices (no barrier touch): only entries with a full
    # horizon_bars window ahead get the vertical label; the last horizon_bars
    # rows cannot observe a full horizon and are dropped (spec section 7)
    n = 20
    horizon = 12
    closes = [100.0] * n
    highs = [100.2] * n
    lows = [99.8] * n
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=horizon)
    )
    for i in range(n - horizon):
        assert labels.iloc[i]["barrier_label"] == 0
        assert labels.iloc[i]["touch_type"] == "vertical"
    for i in range(n - horizon, n):
        assert pd.isna(labels.iloc[i]["barrier_label"])


def test_ambiguous_bar_resolves_lower_first() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    highs[2] = 105.0  # same bar crosses both barriers
    lows[2] = 97.0
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12,
                                  ambiguous_bar_resolution="lower_first")
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "lower"


def test_vertical_barrier_does_not_cross_session_boundary() -> None:
    # two sessions back-to-back; an entry near the end of session 1 cannot
    # observe a full horizon without crossing into session 2, so it is dropped
    # (NaN) -- never labeled from session 2's bars
    idx1 = pd.date_range("2025-01-02T20:30:00Z", periods=6, freq="5min", tz="UTC")  # ends 15:55 ET
    idx2 = pd.date_range("2025-01-03T14:30:00Z", periods=6, freq="5min", tz="UTC")
    idx = idx1.append(idx2)
    closes = [100.0] * 12
    highs = [100.2] * 6 + [200.0] * 6  # session 2 has a huge spike
    lows = [99.8] * 12
    frame = pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes,
         "volume": [1000.0] * 12, "is_rth": [True] * 12},
        index=idx,
    )
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    # entry at the first session-1 bar must NOT be labeled from the session-2
    # spike, and must be dropped because its full horizon is unobservable
    assert pd.isna(labels.loc[idx1[0], "barrier_label"])
