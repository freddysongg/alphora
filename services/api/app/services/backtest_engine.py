"""Bar-by-bar event-driven backtest engine (spec §6.3).

Public surface:
  - SlippageModel, CommissionModel — pessimistic cost defaults.
  - Trade, BacktestResult — engine output dataclasses.
  - simulate(bars, strategy, params, ...) -> BacktestResult — pure-function engine.
  - run_backtest(session, ...) — DB orchestrator: load + simulate + persist.

The engine is pure-function: it takes a pandas DataFrame (OHLCV + UTC
DatetimeIndex) and a `Strategy` Protocol implementation, walks bar-by-bar,
defers fills to the next bar's open (no peeking — spec §6.3 explicit),
and returns a structured result. Persistence is a separate function so
unit tests run without a DB.

Source-bot reference: `/Users/freddy/conductor/workspaces/topStepx/hanoi/
lib/backtest.js` (futures bot). We mirror the bar-by-bar event-driven
shape but NOT: same-bar-close fills, daily caps, EOD flatten,
trail/break-even/take-profit, pressure exit, trend-flip exit. Those
are runner-only concerns (Phase 4+). Backtest is pure signal evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy, StrategyParams


@dataclass(frozen=True)
class SlippageModel:
    """Per-share-per-side slippage in cents.

    Default -2¢/share per fill per spec §6.3. Applied to each fill so a
    round-trip pays 2*per_share_cents/100 dollars per share against the
    trader. A buy fills above reference; a sell fills below.
    """

    per_share_cents: float = 2.0

    def apply_to_fill(self, *, reference_price: float, side: int) -> float:
        if side == 0:
            return reference_price
        sign = 1 if side > 0 else -1
        return reference_price + sign * (self.per_share_cents / 100.0)


@dataclass(frozen=True)
class CommissionModel:
    """Per-fill commission in USD.

    Default $0 per spec §6.3. Both an entry fill and an exit fill each
    pay one `per_trade_usd` cost (a round-trip trade pays
    2 * per_trade_usd in commissions).
    """

    per_trade_usd: float = 0.0

    def cost_per_fill(self) -> float:
        return self.per_trade_usd


TradeExitReason = Literal["signal", "final-bar"]


@dataclass(frozen=True)
class Trade:
    """One completed round-trip trade.

    `side` is +1 (long) or -1 (short). `shares` is a positive count.
    `pnl_usd` = (exit_price - entry_price) * side * shares  - 2 * commission.
    """

    side: int
    entry_bar_index: int
    exit_bar_index: int
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl_usd: float
    bars_held: int
    exit_reason: TradeExitReason


@dataclass(frozen=True)
class BacktestResult:
    """Engine output (spec §6.3).

    `equity_per_bar` is cumulative realized + open-trade-mark P&L in USD
    after each bar, aligned 1:1 with the input `bars` index. The
    persistence step samples this into a daily series for the
    `backtest_equity` table.
    """

    bar_count: int
    trades: list[Trade]
    equity_per_bar: list[float]
    max_drawdown_usd: float
    net_pnl_usd: float
    win_count: int
    loss_count: int
    profit_factor: float | None


def simulate(
    *,
    bars: pd.DataFrame,
    strategy: Strategy,
    params: StrategyParams,
    slippage: SlippageModel | None = None,
    commission: CommissionModel | None = None,
    position_size_shares: int = 1,
) -> BacktestResult:
    """Bar-by-bar event-driven simulator (spec §6.3).

    For each bar `i`:
      1. Call `strategy.evaluate(bars_view, {}, current_position_shares, params)`
         where `bars_view = bars.iloc[: i + 1]`.
      2. If the strategy's `target` (in {-1, 0, +1}) differs from the
         current bias, defer the fill to bar `i+1`'s open ± slippage. If
         `i` is the last bar, no entry (no peeking). The next bar's open
         becomes a real exit/entry on iteration `i+1`.
      3. At the end of the series, force-close any open position at the
         last bar's close ± slippage (mirrors source bot's tail-handling).

    Returns a `BacktestResult` with the trade log, per-bar equity, and
    summary stats. The engine is pure — no DB, no broker, no logging side
    effects.
    """
    if slippage is None:
        slippage = SlippageModel()
    if commission is None:
        commission = CommissionModel()
    bar_count = len(bars)
    if bar_count == 0:
        return BacktestResult(
            bar_count=0,
            trades=[],
            equity_per_bar=[],
            max_drawdown_usd=0.0,
            net_pnl_usd=0.0,
            win_count=0,
            loss_count=0,
            profit_factor=None,
        )
    raise NotImplementedError("simulate body is added in Task 7")


__all__ = [
    "BacktestResult",
    "CommissionModel",
    "SlippageModel",
    "Trade",
    "TradeExitReason",
    "simulate",
]
