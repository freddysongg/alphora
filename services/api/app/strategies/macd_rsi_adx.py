"""MACD+RSI+ADX strategy — port of `filtered` from the source Node bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies.js
        (function `filteredMacdRsiStrategy`, registered as
        `STRATEGIES.filtered`).

Behavior (single-timeframe; entries gated, exits unfiltered):
  - Inner signal: MACD signal-line crossover, confirmed by RSI on the
    same side of the midline (RSI > 50 for long, RSI < 50 for short).
  - Carry-by-default: if already in a position, return inner signal
    without any filters (so a stale ADX or off-hours bar can't trap us).
  - Gate A (entries only): RTH (US Regular Trading Hours; the JS impl
    uses 13:30–20:00 UTC, which is EDT 9:30–16:00 ET; this port
    matches the JS convention for golden-output parity).
  - Gate B (entries only): ADX(14) >= 25 once at least 30 bars are
    available. Below 30 bars, no ADX gate (warmup pass-through).

Phase 1 acceptance: bar-for-bar match against captured outputs from the
source bot on a fixed synthetic input series.
"""
from __future__ import annotations

from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)


class MacdRsiAdxStrategy:
    key: str = "macd_rsi_adx"
    name: str = "MACD+RSI+ADX"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = True

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        raise NotImplementedError("evaluate is implemented in later Phase 1 tasks")
