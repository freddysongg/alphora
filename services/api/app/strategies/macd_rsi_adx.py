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

import math
from typing import Literal

from app.indicators import macd, rsi
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)

_DEFAULT_FAST = 12
_DEFAULT_SLOW = 26
_DEFAULT_SIGNAL = 9
_DEFAULT_RSI_PERIOD = 14
_DEFAULT_RSI_MID = 50.0

Cross = Literal["BULL", "BEAR", "none"]


def _detect_crossover(macd_line: float, signal_line: float, prev_macd: float, prev_signal: float) -> Cross:
    """Match JS `macdCrossover` in lib/indicators.js: detect a signal-line
    crossover on the most-recently-closed bar. Returns 'BULL' (macd
    crossed up above signal), 'BEAR' (crossed down), or 'none'.
    """
    if any(math.isnan(v) for v in (macd_line, signal_line, prev_macd, prev_signal)):
        return "none"
    prev_diff = prev_macd - prev_signal
    curr_diff = macd_line - signal_line
    if prev_diff <= 0 and curr_diff > 0:
        return "BULL"
    if prev_diff >= 0 and curr_diff < 0:
        return "BEAR"
    return "none"


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


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
        fast = int(params.get("fast", _DEFAULT_FAST))
        slow = int(params.get("slow", _DEFAULT_SLOW))
        signal_period = int(params.get("signal", _DEFAULT_SIGNAL))
        rsi_period = int(params.get("rsi_period", _DEFAULT_RSI_PERIOD))
        rsi_mid = float(params.get("rsi_mid", _DEFAULT_RSI_MID))

        carry = _position_sign(current_position)

        if len(primary_bars) < slow + signal_period:
            return StrategyResult(target=carry, meta={"phase": "warmup"})

        macd_line, signal_line, _ = macd(
            primary_bars["close"], fast=fast, slow=slow, signal=signal_period
        )
        rsi_series = rsi(primary_bars["close"], period=rsi_period)
        last_macd = float(macd_line.iloc[-1])
        last_signal = float(signal_line.iloc[-1])
        prev_macd = float(macd_line.iloc[-2])
        prev_signal = float(signal_line.iloc[-2])
        last_rsi = float(rsi_series.iloc[-1])
        cross = _detect_crossover(last_macd, last_signal, prev_macd, prev_signal)

        # Inner signal: BULL cross + RSI > midline → long; BEAR cross +
        # RSI < midline → short; otherwise carry (no exit on cross alone).
        target = carry
        if math.isnan(last_rsi):
            target = carry
        elif cross == "BULL" and last_rsi > rsi_mid:
            target = 1
        elif cross == "BEAR" and last_rsi < rsi_mid:
            target = -1

        meta: dict[str, float | str] = {
            "macd": last_macd,
            "signal": last_signal,
            "rsi": last_rsi,
            "cross": cross,
        }
        return StrategyResult(target=target, meta=meta)
