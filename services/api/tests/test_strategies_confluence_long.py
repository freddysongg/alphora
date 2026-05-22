from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Bars, Strategy, Timeframe, TrailSpec
from app.strategies.confluence_long import ConfluenceLongStrategy


def _bars(*, n: int, start_price: float = 100.0, step: float = 0.05) -> pd.DataFrame:
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [base + timedelta(minutes=i) for i in range(n)]
    closes = [start_price + step * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_strategy_static_metadata() -> None:
    s = ConfluenceLongStrategy()
    assert s.key == "confluence_long"
    assert s.name == "Confluence-Long"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == ["5min"]
    assert s.requires_rth is False


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = ConfluenceLongStrategy()
    assert s.key == "confluence_long"


def test_warmup_when_insufficient_primary_bars() -> None:
    s = ConfluenceLongStrategy()
    primary = _bars(n=10)
    secondary: dict[Timeframe, Bars] = {"5min": _bars(n=2)}
    r = s.evaluate(
        primary_bars=primary, secondary_bars=secondary, current_position=0, params={}
    )
    assert r.target == 0
    assert r.meta.get("phase") == "warmup"


def test_carry_long_position_emits_trail_spec() -> None:
    from app.services.timeframes import resample_bars_to_timeframe

    s = ConfluenceLongStrategy()
    primary = _bars(n=200)
    secondary: dict[Timeframe, Bars] = {"5min": resample_bars_to_timeframe(primary, "5min")}
    r = s.evaluate(
        primary_bars=primary,
        secondary_bars=secondary,
        current_position=1,
        params={},
    )
    assert r.target == 1
    assert r.meta.get("phase") == "holding"


def test_trail_spec_returned_when_entering_long() -> None:
    s = ConfluenceLongStrategy()
    primary = _bars(n=200)
    secondary: dict[Timeframe, Bars] = {"5min": _bars(n=40, start_price=100.0, step=0.5)}
    r = s.evaluate(
        primary_bars=primary,
        secondary_bars=secondary,
        current_position=0,
        params={},
    )
    if r.target == 1:
        assert isinstance(r.trail, TrailSpec)
        assert r.trail.atr_period == 14
        assert r.trail.atr_multiplier > 0


def test_no_secondary_returns_warmup_for_adx() -> None:
    s = ConfluenceLongStrategy()
    primary = _bars(n=200)
    secondary: dict[Timeframe, Bars] = {"5min": _bars(n=5)}
    r = s.evaluate(
        primary_bars=primary,
        secondary_bars=secondary,
        current_position=0,
        params={},
    )
    assert r.target == 0
