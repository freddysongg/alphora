from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


def test_strategy_static_metadata_matches_spec() -> None:
    strat = MacdRsiAdxStrategy()
    assert strat.key == "macd_rsi_adx"
    assert strat.name == "MACD+RSI+ADX"
    assert strat.primary_timeframe == "1min"
    assert strat.secondary_timeframes == []
    assert strat.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = MacdRsiAdxStrategy()
    assert s.key == "macd_rsi_adx"


def _ramp_bars(n: int, *, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [base + timedelta(minutes=i) for i in range(n)]
    closes = [start + step * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.25 for c in closes],
            "low": [c - 0.25 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_evaluate_returns_flat_when_insufficient_bars() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(5)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert result.target == 0
    assert isinstance(result.meta, dict)


def test_evaluate_carry_long_when_no_cross() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(40)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=10, params={}
    )
    assert result.target == 1


def test_evaluate_carry_short_when_no_cross() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(40, start=200.0, step=-0.5)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=-10, params={}
    )
    assert result.target == -1


def test_evaluate_records_macd_diagnostics_in_meta() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(40)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert "macd" in result.meta
    assert "signal" in result.meta
    assert isinstance(result.meta["macd"], float)
    assert not math.isnan(float(result.meta["macd"]))
