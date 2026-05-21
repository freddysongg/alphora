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


def _choppy_bars(n: int, *, start_utc: datetime) -> pd.DataFrame:
    """Sideways saw-tooth: ADX stays low (chop)."""
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        price += 0.1 if i % 2 == 0 else -0.1
        closes.append(price)
    idx = [start_utc + timedelta(minutes=i) for i in range(n)]
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


def test_evaluate_adx_gate_blocks_entries_in_chop() -> None:
    """Sideways input → ADX < 25 → gate must block any new entry."""
    strat = MacdRsiAdxStrategy()
    # All bars inside RTH so the RTH gate doesn't preempt the ADX check.
    bars = _choppy_bars(50, start_utc=datetime(2026, 6, 15, 14, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert result.target == 0
    # Either ADX gated or no cross — but if no cross we want explicit ADX
    # record in meta when bars >= 30:
    if result.meta.get("gate") == "lowAdx":
        assert "adx" in result.meta


def test_evaluate_adx_records_adx_value_when_available() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _bars_at_utc(40, start_utc=datetime(2026, 6, 15, 14, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    assert "adx" in result.meta


def test_evaluate_adx_gate_skipped_when_already_in_position() -> None:
    """While long in a chop session, exits remain unfiltered — the ADX
    gate must not fire; the inner signal (which may flip) passes through."""
    strat = MacdRsiAdxStrategy()
    bars = _choppy_bars(50, start_utc=datetime(2026, 6, 15, 14, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=10, params={}
    )
    # The gate must NOT trigger — whatever the inner signal says is fine.
    assert result.meta.get("gate") != "lowAdx"
    assert result.target != 0 or result.meta.get("gate") is not None


def test_evaluate_adx_skipped_when_bars_below_threshold() -> None:
    """Fewer than 30 bars: no ADX gate applies, inner signal passes
    through. (Matches the JS `bars.length >= 30` check.)"""
    strat = MacdRsiAdxStrategy()
    bars = _bars_at_utc(28, start_utc=datetime(2026, 6, 15, 14, 0, tzinfo=UTC))
    result = strat.evaluate(
        primary_bars=bars, secondary_bars={}, current_position=0, params={}
    )
    # 28 < 30 bars + 26 MACD warmup → likely "warmup" phase.
    # Either way, the ADX gate should NOT be the reason for any flat.
    assert result.meta.get("gate") != "lowAdx"


import json
from pathlib import Path


_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_input_bars() -> pd.DataFrame:
    raw = json.loads((_FIXTURES_DIR / "macd_rsi_adx_input_bars.json").read_text())
    timestamps = [datetime.fromtimestamp(int(b["t"]) / 1000.0, tz=UTC) for b in raw]
    return pd.DataFrame(
        {
            "open": [float(b["o"]) for b in raw],
            "high": [float(b["h"]) for b in raw],
            "low": [float(b["l"]) for b in raw],
            "close": [float(b["c"]) for b in raw],
            "volume": [float(b["v"]) for b in raw],
        },
        index=pd.DatetimeIndex(timestamps, tz="UTC"),
    )


def _load_golden() -> list[dict[str, object]]:
    raw: list[dict[str, object]] = json.loads(
        (_FIXTURES_DIR / "macd_rsi_adx_golden.json").read_text()
    )
    return raw


def test_macd_rsi_adx_matches_source_bot_bar_for_bar() -> None:
    """Phase 1 acceptance: Python evaluate() produces the same `target`
    per bar as the Node `filtered` strategy on the committed input series.

    Iteration model: start flat (current_position=0). After each bar,
    set current_position = previous_target. This matches the no-friction
    simulator the Node fixture-generator uses.
    """
    strat = MacdRsiAdxStrategy()
    bars = _load_input_bars()
    golden = _load_golden()
    assert len(bars) == len(golden), "fixture length mismatch — regenerate both files"

    current_position = 0
    mismatches: list[str] = []
    for i in range(len(bars)):
        primary = bars.iloc[: i + 1]
        result = strat.evaluate(
            primary_bars=primary,
            secondary_bars={},
            current_position=current_position,
            params={},
        )
        expected_target = int(golden[i]["target"])  # type: ignore[call-overload]
        expected_pos_in = int(golden[i]["current_pos_in"])  # type: ignore[call-overload]
        if current_position != expected_pos_in:
            mismatches.append(
                f"bar {i}: current_position_in mismatch (py={current_position}, "
                f"node={expected_pos_in})"
            )
        if result.target != expected_target:
            mismatches.append(
                f"bar {i}: target mismatch (py={result.target}, node={expected_target}, "
                f"meta={result.meta})"
            )
        current_position = result.target

    if mismatches:
        msg = "\n  ".join(mismatches[:10])
        total = len(mismatches)
        raise AssertionError(
            f"golden-output regression: {total} mismatch(es). First 10:\n  {msg}"
        )
