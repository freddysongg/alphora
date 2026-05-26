from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.ict import IctStrategy

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _bars_from_ohlc(
    ohlc: list[tuple[float, float, float, float]], *, base: datetime
) -> pd.DataFrame:
    idx = [base + timedelta(minutes=i) for i in range(len(ohlc))]
    return pd.DataFrame(
        {
            "open":   [o for o, _, _, _ in ohlc],
            "high":   [h for _, h, _, _ in ohlc],
            "low":    [low for _, _, low, _ in ohlc],
            "close":  [c for _, _, _, c in ohlc],
            "volume": [1000.0] * len(ohlc),
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_strategy_static_metadata() -> None:
    s = IctStrategy()
    assert s.key == "ict"
    assert s.name == "ICT"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == []
    assert s.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = IctStrategy()
    assert s.key == "ict"


def test_offhours_returns_flat() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 50,
        base=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "offhours"


def test_carry_position_through_rth_holding_phase() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 50,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=10, params={})
    assert r.target == 1
    assert r.meta.get("phase") == "holding"


def test_no_confluence_returns_flat_when_flat_and_no_setup() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 30,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") in {"no-confluence", "warmup"}


def test_warmup_when_below_threshold_bars() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 5,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "warmup"


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


def test_ict_matches_source_bot_bar_for_bar() -> None:
    s = IctStrategy()
    bars = _load_input_bars("ict")
    golden = _load_golden("ict")
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
            f"ict golden-output regression: {total} mismatch(es). First 10:\n  {msg}"
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


def test_ict_30day_spy_backtest_completes_with_sensible_log() -> None:
    bars = _load_spy_30day_fixture()
    result = simulate(bars=bars, strategy=IctStrategy(), params={})
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
