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


def _zigzag_bars(n: int, *, start: float = 100.0) -> pd.DataFrame:
    """Sequence that produces RSI just under 50 on the latest bar — this
    is the scenario where the JS code suppresses a BULL cross because
    RSI hasn't confirmed.
    """
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    closes: list[float] = []
    price = start
    for i in range(n):
        step = -1.0 if i % 3 == 0 else 0.3
        price += step
        closes.append(price)
    idx = [base + timedelta(minutes=i) for i in range(n)]
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


def test_evaluate_records_rsi_in_meta() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(40)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert "rsi" in result.meta
    assert isinstance(result.meta["rsi"], float)


def test_evaluate_rsi_midline_blocks_unconfirmed_cross() -> None:
    """A BULL MACD cross with RSI <= 50 should NOT flip target to long.

    Construct a series that ramps down then a small final pop — MACD may
    flip BULL but RSI stays below 50 because the dominant recent move was
    down. The strategy must respect the JS midline-confirmation rule.
    """
    strat = MacdRsiAdxStrategy()
    bars = _zigzag_bars(60)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert result.target in (0, -1)


def test_evaluate_records_rsi_value() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars(40)
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    rsi_value = float(result.meta["rsi"])
    assert rsi_value > 50.0


def _bars_at_utc(n: int, *, start_utc: datetime, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    idx = [start_utc + timedelta(minutes=i) for i in range(n)]
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


def test_evaluate_rth_gate_blocks_new_entries_offhours() -> None:
    """At 12:00 UTC (08:00 ET — before RTH open at 09:30 ET) any new
    entry must be flat regardless of MACD/RSI."""
    strat = MacdRsiAdxStrategy()
    # 40 ramping bars ending at 12:39 UTC — fully outside RTH.
    bars = _bars_at_utc(40, start_utc=datetime(2026, 6, 15, 12, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert result.target == 0
    assert result.meta.get("gate") == "offhours"


def test_evaluate_rth_gate_passes_during_rth_window() -> None:
    """At 14:00 UTC (10:00 ET — well inside RTH) the gate must NOT block."""
    strat = MacdRsiAdxStrategy()
    bars = _bars_at_utc(40, start_utc=datetime(2026, 6, 15, 14, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    # The RTH gate must not have flagged off-hours.
    assert result.meta.get("gate") != "offhours"


def test_evaluate_rth_gate_skipped_when_already_in_position() -> None:
    """While long, an off-hours bar must NOT force flat — exits are
    unfiltered. Carry the inner-signal result."""
    strat = MacdRsiAdxStrategy()
    bars = _bars_at_utc(40, start_utc=datetime(2026, 6, 15, 12, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=10, params={}
    )
    # Carry the long bias; gate should NOT trigger.
    assert result.target == 1
    assert result.meta.get("gate") != "offhours"
