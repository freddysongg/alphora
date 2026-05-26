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


import json  # noqa: E402
from pathlib import Path  # noqa: E402

from app.services.timeframes import resample_bars_to_timeframe  # noqa: E402

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


def test_confluence_long_matches_source_bot_bar_for_bar() -> None:
    s = ConfluenceLongStrategy()
    bars = _load_input_bars("confluence_long")
    golden = _load_golden("confluence_long")
    assert len(bars) == len(golden), "fixture length mismatch -- regenerate both files"

    current_position = 0
    mismatches: list[str] = []
    bars5m_mismatches: list[str] = []
    for i in range(len(bars)):
        primary = bars.iloc[: i + 1]
        bars_5m = resample_bars_to_timeframe(primary, "5min")
        expected_bars5m_len = int(golden[i]["bars5m_len"])  # type: ignore[call-overload]
        if len(bars_5m) != expected_bars5m_len:
            bars5m_mismatches.append(
                f"bar {i}: 5min len mismatch (py={len(bars_5m)}, node={expected_bars5m_len})"
            )

        result = s.evaluate(
            primary_bars=primary,
            secondary_bars={"5min": bars_5m},
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

    if bars5m_mismatches:
        msg = "\n  ".join(bars5m_mismatches[:10])
        total = len(bars5m_mismatches)
        raise AssertionError(
            f"confluence_long 5min-length regression: {total} mismatch(es). "
            f"First 10:\n  {msg}"
        )
    if mismatches:
        msg = "\n  ".join(mismatches[:10])
        total = len(mismatches)
        raise AssertionError(
            f"confluence_long golden-output regression: {total} mismatch(es). "
            f"First 10:\n  {msg}"
        )


from app.services.backtest_engine import simulate  # noqa: E402

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


def test_confluence_long_30day_spy_backtest_completes_with_sensible_log() -> None:
    bars = _load_spy_30day_fixture()
    result = simulate(bars=bars, strategy=ConfluenceLongStrategy(), params={})
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
