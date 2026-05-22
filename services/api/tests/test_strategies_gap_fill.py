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


import json  # noqa: E402
from pathlib import Path  # noqa: E402

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


def test_gap_fill_matches_source_bot_bar_for_bar() -> None:
    s = GapFillStrategy()
    bars = _load_input_bars("gap_fill")
    golden = _load_golden("gap_fill")
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
            f"gap_fill golden-output regression: {total} mismatch(es). First 10:\n  {msg}"
        )


from app.services.backtest_engine import simulate  # noqa: E402,F811

_SPY_FIXTURE = _FIXTURES_DIR / "spy_30day_1min.json"


def _load_spy_30day_fixture() -> pd.DataFrame:
    raw = json.loads(_SPY_FIXTURE.read_text())
    timestamps = [pd.Timestamp(int(b["t"]), unit="ms", tz="UTC") for b in raw]
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


def test_gap_fill_30day_spy_backtest_completes_with_sensible_log() -> None:
    bars = _load_spy_30day_fixture()
    result = simulate(
        bars=bars,
        strategy=GapFillStrategy(),
        params={"min_gap_pts": 0.05},
    )
    assert result.bar_count == 11_700
    assert len(result.equity_per_bar) == 11_700
    prev_exit_idx = -1
    for t in result.trades:
        assert t.entry_price > 0.0
        assert t.exit_price > 0.0
        assert t.shares > 0
        assert t.bars_held >= 0
        assert t.entry_bar_index <= t.exit_bar_index
        assert t.entry_bar_index >= prev_exit_idx
        prev_exit_idx = t.exit_bar_index
        assert t.exit_ts >= t.entry_ts
    sum_pnl = sum(t.pnl_usd for t in result.trades)
    assert abs(sum_pnl - result.net_pnl_usd) < 1e-6
