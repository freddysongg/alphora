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


__all__ = ["CommissionModel", "SlippageModel"]
