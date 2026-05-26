"""ORB-safe strategy -- port of `orbsafe` from the source Node bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies.js
        (function `orbSafeStrategy`, registered as `STRATEGIES.orbsafe`).

Behavior (single-timeframe; session-aware):
  - Opening range = high/low of bars whose ET minute-of-day is in
    [or_start, or_end) (default 09:30-10:00).
  - No new entries before or_end (still in OR) or after morning cutoff
    (default 11:30 ET) -- entry window is [or_end, morning_cutoff).
  - Force flat at flat_at (default 15:30 ET) -- `target=0` regardless
    of position; also returns flat before or_start (pre-RTH).
  - VWAP direction gate: long breakout only if close > current
    session VWAP; short only if close < VWAP. Otherwise reject.
  - Carry: while in position (any time), return current bias with
    phase='holding'.
"""
from __future__ import annotations

import math

from app.indicators import vwap
from app.services.market_clock import (
    MORNING_CUTOFF_ET_MIN,
    RTH_OPEN_ET_MIN,
    to_et,
)
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)

_DEFAULT_OR_START_MIN = RTH_OPEN_ET_MIN
_DEFAULT_OR_END_MIN = 10 * 60
_DEFAULT_CUTOFF_MIN = MORNING_CUTOFF_ET_MIN
_DEFAULT_FLAT_MIN = 15 * 60 + 30


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


class OrbSafeStrategy:
    key: str = "orb_safe"
    name: str = "ORB-safe"
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
        or_start = int(params.get("or_start_et_min", _DEFAULT_OR_START_MIN))
        or_end = int(params.get("or_end_et_min", _DEFAULT_OR_END_MIN))
        cutoff = int(params.get("cutoff_et_min", _DEFAULT_CUTOFF_MIN))
        flat_at = int(params.get("flat_at_et_min", _DEFAULT_FLAT_MIN))

        if len(primary_bars) == 0:
            return StrategyResult(target=_position_sign(current_position), meta={})

        last_ts = primary_bars.index[-1]
        last_clock = to_et(last_ts)
        last_close = float(primary_bars["close"].iloc[-1])

        if last_clock.minutes >= flat_at or last_clock.minutes < or_start:
            return StrategyResult(target=0, meta={"phase": "offhours"})

        today = last_clock.day
        or_high = float("-inf")
        or_low = float("inf")
        or_bars = 0
        for j in range(len(primary_bars) - 1, -1, -1):
            clock = to_et(primary_bars.index[j])
            if clock.day != today:
                break
            if or_start <= clock.minutes < or_end:
                h = float(primary_bars["high"].iloc[j])
                low = float(primary_bars["low"].iloc[j])
                if h > or_high:
                    or_high = h
                if low < or_low:
                    or_low = low
                or_bars += 1

        carry = _position_sign(current_position)

        if last_clock.minutes < or_end or or_bars == 0:
            return StrategyResult(target=0, meta={"phase": "opening-range"})

        if last_clock.minutes >= cutoff and carry == 0:
            return StrategyResult(
                target=0,
                meta={"phase": "past-morning-cutoff", "or_high": or_high, "or_low": or_low},
            )

        if carry != 0:
            return StrategyResult(
                target=carry,
                meta={"phase": "holding", "or_high": or_high, "or_low": or_low},
            )

        vwap_series = vwap(primary_bars)
        v = float(vwap_series.iloc[-1])

        if last_close > or_high:
            if not math.isnan(v) and last_close > v:
                return StrategyResult(
                    target=1,
                    meta={
                        "phase": "breakout",
                        "or_high": or_high,
                        "or_low": or_low,
                        "vwap": v,
                        "close": last_close,
                    },
                )
            return StrategyResult(
                target=0,
                meta={
                    "phase": "vwap-reject-long",
                    "or_high": or_high,
                    "or_low": or_low,
                    "vwap": v if not math.isnan(v) else "NaN",
                    "close": last_close,
                },
            )

        if last_close < or_low:
            if not math.isnan(v) and last_close < v:
                return StrategyResult(
                    target=-1,
                    meta={
                        "phase": "breakout",
                        "or_high": or_high,
                        "or_low": or_low,
                        "vwap": v,
                        "close": last_close,
                    },
                )
            return StrategyResult(
                target=0,
                meta={
                    "phase": "vwap-reject-short",
                    "or_high": or_high,
                    "or_low": or_low,
                    "vwap": v if not math.isnan(v) else "NaN",
                    "close": last_close,
                },
            )

        return StrategyResult(
            target=0,
            meta={
                "phase": "waiting",
                "or_high": or_high,
                "or_low": or_low,
                "vwap": v if not math.isnan(v) else "NaN",
                "close": last_close,
            },
        )
