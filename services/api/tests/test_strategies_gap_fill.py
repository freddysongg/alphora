from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.gap_fill import GapFillStrategy


def _bars(*, day: datetime, n: int, closes: list[float]) -> pd.DataFrame:
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
    s = GapFillStrategy()
    assert s.key == "gap_fill"
    assert s.name == "GapFill"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == []
    assert s.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = GapFillStrategy()
    assert s.key == "gap_fill"


def test_warmup_when_no_prior_day_data() -> None:
    s = GapFillStrategy()
    bars = _bars(
        day=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
        n=60,
        closes=[100.0 + i * 0.01 for i in range(60)],
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") in {"no-gap-info", "warmup", "wait"}


def test_pre_window_returns_wait() -> None:
    s = GapFillStrategy()
    day1 = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    day2 = datetime(2026, 6, 16, 13, 30, tzinfo=UTC)
    bars1 = [
        {"o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "t": day1 + timedelta(minutes=i)}
        for i in range(390)
    ]
    bars2 = [
        {"o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "t": day2 + timedelta(minutes=i)}
        for i in range(6)
    ]
    all_bars = bars1 + bars2
    df = pd.DataFrame(
        {
            "open":   [b["o"] for b in all_bars],
            "high":   [b["h"] for b in all_bars],
            "low":    [b["l"] for b in all_bars],
            "close":  [b["c"] for b in all_bars],
            "volume": [1000.0] * len(all_bars),
        },
        index=pd.DatetimeIndex([b["t"] for b in all_bars], tz="UTC"),
    )
    r = s.evaluate(primary_bars=df, secondary_bars={}, current_position=0, params={})
    assert r.target == 0


def test_force_flat_at_cutoff_when_holding() -> None:
    s = GapFillStrategy()
    day1 = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    day2 = datetime(2026, 6, 16, 13, 30, tzinfo=UTC)
    bars: list[dict[str, float | datetime]] = []
    for i in range(390):
        bars.append({"o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "t": day1 + timedelta(minutes=i)})
    for i in range(271):
        bars.append({"o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "t": day2 + timedelta(minutes=i)})
    df = pd.DataFrame(
        {
            "open":   [b["o"] for b in bars],
            "high":   [b["h"] for b in bars],
            "low":    [b["l"] for b in bars],
            "close":  [b["c"] for b in bars],
            "volume": [1000.0] * len(bars),
        },
        index=pd.DatetimeIndex([b["t"] for b in bars], tz="UTC"),
    )
    r = s.evaluate(primary_bars=df, secondary_bars={}, current_position=10, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "eod-flat"
