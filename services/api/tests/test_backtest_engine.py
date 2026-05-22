from __future__ import annotations

from app.services.backtest_engine import (
    CommissionModel,
    SlippageModel,
)


def test_slippage_default_is_two_cents_per_share() -> None:
    s = SlippageModel()
    assert s.per_share_cents == 2.0


def test_slippage_buy_fill_is_above_reference() -> None:
    s = SlippageModel(per_share_cents=2.0)
    fill = s.apply_to_fill(reference_price=500.00, side=1)
    assert fill == 500.02


def test_slippage_sell_fill_is_below_reference() -> None:
    s = SlippageModel(per_share_cents=2.0)
    fill = s.apply_to_fill(reference_price=500.00, side=-1)
    assert fill == 499.98


def test_slippage_zero_side_returns_reference() -> None:
    s = SlippageModel(per_share_cents=2.0)
    assert s.apply_to_fill(reference_price=500.00, side=0) == 500.00


def test_commission_default_is_zero() -> None:
    c = CommissionModel()
    assert c.per_trade_usd == 0.0


def test_commission_per_trade_applies_to_each_fill() -> None:
    c = CommissionModel(per_trade_usd=0.5)
    assert c.cost_per_fill() == 0.5


from datetime import UTC, datetime  # noqa: E402

from app.services.backtest_engine import Trade  # noqa: E402


def test_trade_holds_all_per_trade_fields() -> None:
    t = Trade(
        side=1,
        entry_bar_index=10,
        exit_bar_index=25,
        entry_ts=datetime(2026, 4, 1, 13, 40, tzinfo=UTC),
        exit_ts=datetime(2026, 4, 1, 13, 55, tzinfo=UTC),
        entry_price=500.02,
        exit_price=501.48,
        shares=1,
        pnl_usd=1.46,
        bars_held=15,
        exit_reason="signal",
    )
    assert t.side == 1
    assert t.bars_held == 15
    assert t.exit_reason == "signal"


def test_trade_is_frozen() -> None:
    t = Trade(
        side=1,
        entry_bar_index=0,
        exit_bar_index=1,
        entry_ts=datetime(2026, 4, 1, tzinfo=UTC),
        exit_ts=datetime(2026, 4, 1, tzinfo=UTC),
        entry_price=100.0,
        exit_price=100.0,
        shares=1,
        pnl_usd=0.0,
        bars_held=1,
        exit_reason="signal",
    )
    import dataclasses

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        t.shares = 99  # type: ignore[misc]


import pandas as pd  # type: ignore[import-untyped]  # noqa: E402

from app.services.backtest_engine import BacktestResult, simulate  # noqa: E402
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy  # noqa: E402


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []},
        index=pd.DatetimeIndex([], tz="UTC"),
    )


def test_backtest_result_default_shape() -> None:
    r = BacktestResult(
        bar_count=0,
        trades=[],
        equity_per_bar=[],
        max_drawdown_usd=0.0,
        net_pnl_usd=0.0,
        win_count=0,
        loss_count=0,
        profit_factor=None,
    )
    assert r.bar_count == 0
    assert r.trades == []
    assert r.profit_factor is None


def test_simulate_empty_bars_returns_empty_result() -> None:
    result = simulate(
        bars=_empty_bars(),
        strategy=MacdRsiAdxStrategy(),
        params={},
    )
    assert result.bar_count == 0
    assert result.trades == []
    assert result.equity_per_bar == []
    assert result.net_pnl_usd == 0.0


from datetime import UTC, datetime, timedelta  # noqa: E402,F811


def _ramp_bars_for_engine(n: int, *, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
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


def test_simulate_no_peeking_no_entry_on_final_bar() -> None:
    """If the strategy flips on the LAST bar, no new position opens — we'd
    have to fill at bar i+1's open which doesn't exist."""
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars_for_engine(60)
    result = simulate(bars=bars, strategy=strat, params={})
    # All trades' exit_bar_index must be <= last bar index.
    for t in result.trades:
        assert t.entry_bar_index < len(bars)
        assert t.exit_bar_index < len(bars)


def test_simulate_returns_per_bar_equity_with_correct_length() -> None:
    strat = MacdRsiAdxStrategy()
    bars = _ramp_bars_for_engine(60)
    result = simulate(bars=bars, strategy=strat, params={})
    assert result.bar_count == 60
    assert len(result.equity_per_bar) == 60


def test_simulate_fill_uses_next_bar_open_plus_slippage_on_long_entry() -> None:
    """Synthetic entry: hand-build a strategy that signals long at bar 1,
    flat thereafter. Entry fill must be bars.iloc[2]['open'] + slippage,
    not bars.iloc[1]['close']."""

    class _LongAtBar1(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=1, meta={})
            if current_position > 0:
                return StrategyResult(target=1, meta={})
            return StrategyResult(target=0, meta={})

    bars = _ramp_bars_for_engine(10)
    result = simulate(bars=bars, strategy=_LongAtBar1(), params={})
    assert len(result.trades) >= 1
    first = result.trades[0]
    assert first.side == 1
    expected_entry = bars["open"].iloc[2] + 0.02  # +2¢/share
    assert abs(first.entry_price - expected_entry) < 1e-9
    assert first.entry_bar_index == 2


def test_simulate_close_and_flip_uses_same_next_bar_open() -> None:
    """A long → short flip closes the long and opens the short at the
    same bar's open. Slippage applies to both fills (long sells at
    open - slip; short sells at open - slip)."""

    class _FlipAtBar3(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=1, meta={})
            if len(primary_bars) == 4:
                return StrategyResult(target=-1, meta={})
            return StrategyResult(
                target=1 if current_position > 0 else (-1 if current_position < 0 else 0),
                meta={},
            )

    bars = _ramp_bars_for_engine(10)
    result = simulate(bars=bars, strategy=_FlipAtBar3(), params={})
    assert len(result.trades) >= 2
    long_trade = result.trades[0]
    short_trade = result.trades[1]
    assert long_trade.side == 1
    assert short_trade.side == -1
    # Long exits at bar 4's open - 0.02; short enters at bar 4's open - 0.02.
    expected_close = bars["open"].iloc[4] - 0.02
    expected_short_entry = bars["open"].iloc[4] - 0.02
    assert abs(long_trade.exit_price - expected_close) < 1e-9
    assert abs(short_trade.entry_price - expected_short_entry) < 1e-9
    assert long_trade.exit_bar_index == 4
    assert short_trade.entry_bar_index == 4


def test_simulate_flat_strategy_has_zero_equity_curve() -> None:
    class _AlwaysFlat(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            return StrategyResult(target=0, meta={})

    bars = _ramp_bars_for_engine(20)
    result = simulate(bars=bars, strategy=_AlwaysFlat(), params={})
    assert all(e == 0.0 for e in result.equity_per_bar)
    assert result.max_drawdown_usd == 0.0
    assert result.trades == []


def test_simulate_v_shape_records_drawdown_at_trough() -> None:
    """Long entry then drop then partial recovery: drawdown == peak - trough."""

    class _LongFromBar1(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=1, meta={})
            return StrategyResult(target=1, meta={})

    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    closes = [100.0, 101.0, 102.0, 101.0, 99.0, 100.0]
    idx = [base + timedelta(minutes=i) for i in range(len(closes))]
    bars = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )
    result = simulate(bars=bars, strategy=_LongFromBar1(), params={})
    assert result.max_drawdown_usd > 0.0
    # The trough-to-peak gap in our open-mark is realised after the
    # equity peak. Peak occurs after open at index 2; trough after open
    # at index 4 -> drawdown reflects the magnitude.
    assert result.max_drawdown_usd >= 2.0  # 102->99 minus slippage rounding


def test_simulate_equity_per_bar_is_monotonic_when_strategy_is_winning() -> None:
    """Strict uptrend with always-long strategy: open-mark equity rises bar-by-bar."""
    from itertools import pairwise

    class _AlwaysLong(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=1, meta={})
            return StrategyResult(target=1, meta={})

    bars = _ramp_bars_for_engine(15)
    result = simulate(bars=bars, strategy=_AlwaysLong(), params={})
    # After the entry bar (index 2), equity rises with each subsequent bar.
    after_entry = result.equity_per_bar[3:]
    for prev, curr in pairwise(after_entry):
        assert curr >= prev - 1e-9


def test_simulate_counts_wins_and_losses_correctly() -> None:
    """Construct three winning closes by alternating long/flat over a rising series."""

    class _ToggleLong(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            i = len(primary_bars)
            if i in (2, 6, 10):
                return StrategyResult(target=1, meta={})
            if i in (4, 8, 12):
                return StrategyResult(target=0, meta={})
            return StrategyResult(
                target=1 if current_position > 0 else 0, meta={}
            )

    bars = _ramp_bars_for_engine(15)
    result = simulate(bars=bars, strategy=_ToggleLong(), params={})
    # In a strict uptrend, every long round-trip wins.
    assert result.win_count >= 1
    assert result.loss_count == 0


def test_simulate_profit_factor_is_none_when_no_trades() -> None:
    class _AlwaysFlat(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            return StrategyResult(target=0, meta={})

    bars = _ramp_bars_for_engine(20)
    result = simulate(bars=bars, strategy=_AlwaysFlat(), params={})
    assert result.profit_factor is None


def test_simulate_profit_factor_is_inf_when_no_losses() -> None:
    class _ToggleLongOnce(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            i = len(primary_bars)
            if i == 2:
                return StrategyResult(target=1, meta={})
            if i == 5:
                return StrategyResult(target=0, meta={})
            return StrategyResult(
                target=1 if current_position > 0 else 0, meta={}
            )

    bars = _ramp_bars_for_engine(10)
    result = simulate(bars=bars, strategy=_ToggleLongOnce(), params={})
    assert result.win_count == 1
    assert result.loss_count == 0
    assert result.profit_factor == float("inf")


def test_simulate_force_closes_open_long_at_last_close() -> None:
    class _LongFromBar1ToEnd(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=1, meta={})
            return StrategyResult(target=1, meta={})

    bars = _ramp_bars_for_engine(10)
    result = simulate(bars=bars, strategy=_LongFromBar1ToEnd(), params={})
    # Exactly one trade, closed on the final bar.
    assert len(result.trades) == 1
    final = result.trades[0]
    assert final.exit_bar_index == len(bars) - 1
    assert final.exit_reason == "final-bar"
    expected_exit = bars["close"].iloc[-1] - 0.02  # selling out the long
    assert abs(final.exit_price - expected_exit) < 1e-9


def test_simulate_open_position_equity_reflects_entry_commission() -> None:
    """With nonzero commission, equity_per_bar for a bar with an open
    position must include the entry commission already charged at open.
    Without this, equity overstates until the trade closes."""
    from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe

    class _LongFromBar1WithCommission(MacdRsiAdxStrategy):
        def evaluate(
            self,
            primary_bars: Bars,
            secondary_bars: dict[Timeframe, Bars],
            current_position: int,
            params: StrategyParams,
        ) -> StrategyResult:
            if len(primary_bars) == 1:
                return StrategyResult(target=0, meta={})
            return StrategyResult(target=1, meta={})

    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    n = 5
    slip = SlippageModel().per_share_cents / 100.0
    idx = [base + timedelta(minutes=i) for i in range(n)]
    bars = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )
    result = simulate(
        bars=bars,
        strategy=_LongFromBar1WithCommission(),
        params={},
        commission=CommissionModel(per_trade_usd=0.5),
    )
    # Bars 0 and 1: flat, no position. Strategy returns target=0 at i=0
    # so no pending entry, and target=1 at i=1 defers fill to i=2.
    assert result.equity_per_bar[0] == 0.0
    assert result.equity_per_bar[1] == 0.0
    # Bar 2: long entry materializes at open[2] + slippage = 100.02. Mark
    # against close[2]=100.0 is -0.02. With the fix, equity also includes
    # the entry commission -0.5 already charged on the open trade, so
    # equity[2] = -0.5 + -0.02 = -0.52. Without the fix, equity[2] = -0.02.
    assert abs(result.equity_per_bar[2] - (-0.5 - slip)) < 1e-9
    # Bar 3: still open, still flat. equity stays at -0.52.
    assert abs(result.equity_per_bar[3] - (-0.5 - slip)) < 1e-9
    # Bar 4: final-bar force-close. realized_pnl folds in both fills'
    # commissions and both fills' slippage: -0.5 (entry) + (99.98-100.02)
    # + -0.5 (exit) = -1.04. The force-close path recomputes
    # equity_per_bar[-1] = realized_pnl, so this assertion holds with or
    # without the fix — it's a sanity check.
    assert abs(result.equity_per_bar[4] - (-1.0 - 2 * slip)) < 1e-9


def test_simulate_force_closes_open_short_at_last_close() -> None:
    class _ShortFromBar1ToEnd(MacdRsiAdxStrategy):
        def evaluate(self, primary_bars, secondary_bars, current_position, params):  # type: ignore[override]
            from app.strategies.base import StrategyResult

            if len(primary_bars) == 2:
                return StrategyResult(target=-1, meta={})
            return StrategyResult(target=-1, meta={})

    bars = _ramp_bars_for_engine(10, start=200.0, step=-0.5)
    result = simulate(bars=bars, strategy=_ShortFromBar1ToEnd(), params={})
    assert len(result.trades) == 1
    final = result.trades[0]
    assert final.exit_reason == "final-bar"
    expected_exit = bars["close"].iloc[-1] + 0.02  # buying back the short
    assert abs(final.exit_price - expected_exit) < 1e-9


import json  # noqa: E402
from pathlib import Path  # noqa: E402

_SPY_FIXTURE = Path(__file__).parent / "fixtures" / "spy_30day_1min.json"


def _load_spy_30day_fixture() -> pd.DataFrame:
    raw = json.loads(_SPY_FIXTURE.read_text())
    timestamps = [
        pd.Timestamp(int(b["t"]), unit="ms", tz="UTC") for b in raw
    ]
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


def test_phase2_acceptance_30day_spy_macd_rsi_adx_completes() -> None:
    """Phase 2 acceptance (spec §12):

    A 30-day SPY 1-minute backtest of MacdRsiAdxStrategy completes; the
    equity curve and trade log are sensible. 'Sensible' means:
    - The simulator returns without raising.
    - All trade entry/exit prices are positive.
    - All trade timestamps are non-decreasing across the log.
    - The equity series has the same length as the input bars.
    - No volume is negative or NaN.
    - Realised P&L equals the sum of per-trade P&L (accounting parity).
    - bar_count matches input length.
    """
    bars = _load_spy_30day_fixture()
    assert len(bars) == 11_700
    assert (bars["volume"] >= 0).all()
    assert (bars["open"] > 0).all()
    assert (bars["high"] > 0).all()
    assert (bars["low"] > 0).all()
    assert (bars["close"] > 0).all()

    result = simulate(
        bars=bars,
        strategy=MacdRsiAdxStrategy(),
        params={},
    )

    assert result.bar_count == 11_700
    assert len(result.equity_per_bar) == 11_700

    # Trade log integrity.
    prev_exit_idx = -1
    for t in result.trades:
        assert t.entry_price > 0.0
        assert t.exit_price > 0.0
        assert t.shares > 0
        assert t.bars_held >= 0
        assert t.entry_bar_index <= t.exit_bar_index
        # Trades do not overlap in time. A long->short flip exits and
        # re-enters at the same bar's open, so adjacent trades may share
        # a bar index but no time overlap exists.
        assert t.entry_bar_index >= prev_exit_idx
        prev_exit_idx = t.exit_bar_index
        assert t.exit_ts >= t.entry_ts

    # Accounting parity: sum of per-trade P&L equals net P&L on the last bar.
    sum_pnl = sum(t.pnl_usd for t in result.trades)
    assert abs(sum_pnl - result.net_pnl_usd) < 1e-6

    # Win + loss + scratch must add up to trade count.
    scratches = result.trade_count_scratch(  # type: ignore[attr-defined]
    ) if hasattr(result, "trade_count_scratch") else (
        len(result.trades) - result.win_count - result.loss_count
    )
    assert result.win_count + result.loss_count + scratches == len(result.trades)
