from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.orb_safe import OrbSafeStrategy


def _rth_bars(*, day: datetime, n: int, closes: list[float]) -> pd.DataFrame:
    assert len(closes) == n
    idx = [day + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_strategy_static_metadata() -> None:
    s = OrbSafeStrategy()
    assert s.key == "orb_safe"
    assert s.name == "ORB-safe"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == []
    assert s.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = OrbSafeStrategy()
    assert s.key == "orb_safe"


def test_pre_rth_bar_returns_flat_offhours() -> None:
    s = OrbSafeStrategy()
    bars = _rth_bars(
        day=datetime(2026, 6, 15, 13, 0, tzinfo=UTC),
        n=5,
        closes=[100.0, 100.1, 100.2, 100.3, 100.4],
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "offhours"


def test_inside_opening_range_returns_flat_with_phase_meta() -> None:
    s = OrbSafeStrategy()
    bars = _rth_bars(
        day=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
        n=5,
        closes=[100.0, 100.1, 100.2, 100.3, 100.4],
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "opening-range"


def test_past_morning_cutoff_flat_blocks_new_entries() -> None:
    s = OrbSafeStrategy()
    n = 150
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    closes = [100.0 + i * 0.01 for i in range(n)]
    bars = _rth_bars(day=base, n=n, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") in {"past-morning-cutoff", "waiting"}


def test_force_flat_at_eod_when_holding() -> None:
    s = OrbSafeStrategy()
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    n = 361
    closes = [100.0 + i * 0.01 for i in range(n)]
    bars = _rth_bars(day=base, n=n, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=10, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "offhours"


def test_long_breakout_path_returns_valid_target() -> None:
    s = OrbSafeStrategy()
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    or_closes = [100.0] * 30
    closes = or_closes + [100.6]
    bars = _rth_bars(day=base, n=31, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target in (0, 1)
    assert "phase" in r.meta
