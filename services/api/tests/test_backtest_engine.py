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
