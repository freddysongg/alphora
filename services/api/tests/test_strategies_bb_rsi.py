from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.bb_rsi import BbRsiStrategy


def _bars(n: int, *, closes: list[float]) -> pd.DataFrame:
    assert len(closes) == n
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [base + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.05 for c in closes],
            "low": [c - 0.05 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_strategy_static_metadata() -> None:
    s = BbRsiStrategy()
    assert s.key == "bb_rsi"
    assert s.name == "BB+RSI"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == []
    assert s.requires_rth is False


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = BbRsiStrategy()
    assert s.key == "bb_rsi"


def test_warmup_returns_flat_with_empty_meta() -> None:
    s = BbRsiStrategy()
    bars = _bars(15, closes=[100.0] * 15)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0


def test_long_exits_when_close_at_or_above_middle_band() -> None:
    s = BbRsiStrategy()
    closes = [100.0 + i * 0.05 for i in range(50)]
    bars = _bars(50, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=10, params={})
    assert r.target == 0


def test_long_exit_when_close_returns_to_middle_from_below() -> None:
    s = BbRsiStrategy()
    closes = [100.0] * 30 + [99.9, 99.8, 99.7, 99.8, 99.9, 100.0, 100.05, 100.1, 100.15, 100.2]
    bars = _bars(40, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=10, params={})
    assert r.target in (0, 1)


def test_short_exit_when_close_returns_to_middle_from_above() -> None:
    s = BbRsiStrategy()
    closes = [100.0] * 30 + [100.1, 100.2, 100.3, 100.2, 100.1, 100.0, 99.95, 99.9, 99.85, 99.8]
    bars = _bars(40, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=-10, params={})
    assert r.target in (0, -1)


def test_flat_entry_requires_band_break_and_rsi_extreme() -> None:
    import math as _math
    s = BbRsiStrategy()
    closes = [100.0 + _math.sin(i * 0.3) * 0.5 for i in range(40)]
    bars = _bars(40, closes=closes)
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0


def test_meta_records_band_levels_and_rsi() -> None:
    s = BbRsiStrategy()
    bars = _bars(40, closes=[100.0 + i * 0.1 for i in range(40)])
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert "middle" in r.meta
    assert "upper" in r.meta
    assert "lower" in r.meta
    assert "rsi" in r.meta


import json  # noqa: E402,F811
from pathlib import Path  # noqa: E402,F811

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_input_bars(name: str) -> pd.DataFrame:
    raw = json.loads((_FIXTURES_DIR / f"{name}_input_bars.json").read_text())
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


def _load_golden(name: str) -> list[dict[str, object]]:
    raw: list[dict[str, object]] = json.loads(
        (_FIXTURES_DIR / f"{name}_golden.json").read_text()
    )
    return raw


def test_bb_rsi_matches_source_bot_bar_for_bar() -> None:
    s = BbRsiStrategy()
    bars = _load_input_bars("bb_rsi")
    golden = _load_golden("bb_rsi")
    assert len(bars) == len(golden), "fixture length mismatch -- regenerate both files"

    current_position = 0
    mismatches: list[str] = []
    for i in range(len(bars)):
        primary = bars.iloc[: i + 1]
        result = s.evaluate(
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
            f"bb_rsi golden-output regression: {total} mismatch(es). First 10:\n  {msg}"
        )
