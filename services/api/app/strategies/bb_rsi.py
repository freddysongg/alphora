"""BB+RSI strategy -- port of `bbrsi` from the source Node bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies.js
        (function `bbRsiStrategy`, registered as `STRATEGIES.bbrsi`).

Behavior (single-timeframe; mean-reversion; entries require both gates):
  - Indicators: Bollinger Bands(20, 2 sigma) on close, RSI(14) on close.
  - Entry (flat only):
      * close < lower AND RSI < rsiLo (default 30) -> long
      * close > upper AND RSI > rsiHi (default 70) -> short
  - Exit (threshold, mirrors source bot):
      * long position: close >= middle -> flat
      * short position: close <= middle -> flat
  - No RTH gate, no ADX gate, no carry filter -- pure mean-reversion.
"""
from __future__ import annotations

import math

from app.indicators import bollinger, rsi
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)

_DEFAULT_BB_PERIOD = 20
_DEFAULT_BB_MULT = 2.0
_DEFAULT_RSI_PERIOD = 14
_DEFAULT_RSI_LO = 30.0
_DEFAULT_RSI_HI = 70.0


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


class BbRsiStrategy:
    key: str = "bb_rsi"
    name: str = "BB+RSI"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = False

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        bb_period = int(params.get("bb_period", _DEFAULT_BB_PERIOD))
        bb_mult = float(params.get("bb_mult", _DEFAULT_BB_MULT))
        rsi_period = int(params.get("rsi_period", _DEFAULT_RSI_PERIOD))
        rsi_lo = float(params.get("rsi_lo", _DEFAULT_RSI_LO))
        rsi_hi = float(params.get("rsi_hi", _DEFAULT_RSI_HI))

        carry = _position_sign(current_position)

        if len(primary_bars) < max(bb_period, rsi_period + 1):
            return StrategyResult(target=carry, meta={"phase": "warmup"})

        closes = primary_bars["close"]
        middle, upper, lower = bollinger(closes, period=bb_period, mult=bb_mult)
        rsi_series = rsi(closes, period=rsi_period)

        m = float(middle.iloc[-1])
        u = float(upper.iloc[-1])
        lo = float(lower.iloc[-1])
        r = float(rsi_series.iloc[-1])
        c = float(closes.iloc[-1])

        if any(math.isnan(v) for v in (m, u, lo, r)):
            return StrategyResult(target=carry, meta={"phase": "warmup"})

        meta: dict[str, float | str] = {
            "price": c,
            "middle": m,
            "upper": u,
            "lower": lo,
            "rsi": r,
        }

        target = carry
        if carry == 0:
            if c < lo and r < rsi_lo:
                target = 1
            elif c > u and r > rsi_hi:
                target = -1
        elif carry > 0:
            if c >= m:
                target = 0
        else:
            if c <= m:
                target = 0

        return StrategyResult(target=target, meta=meta)
