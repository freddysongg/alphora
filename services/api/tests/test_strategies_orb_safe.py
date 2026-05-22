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


def test_orb_safe_matches_source_bot_bar_for_bar() -> None:
    s = OrbSafeStrategy()
    bars = _load_input_bars("orb_safe")
    golden = _load_golden("orb_safe")
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
                f"py_meta={result.meta}, node_meta={golden[i].get('meta')})"
            )
        current_position = result.target

    if mismatches:
        msg = "\n  ".join(mismatches[:10])
        total = len(mismatches)
        raise AssertionError(
            f"orb_safe golden-output regression: {total} mismatch(es). First 10:\n  {msg}"
        )
