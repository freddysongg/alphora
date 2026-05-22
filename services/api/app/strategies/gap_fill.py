"""GapFill strategy -- port of `gapfill` from the source Node bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies.js
        (function `gapFillStrategy`, registered as `STRATEGIES.gapfill`).

Behavior (single-timeframe; multi-day session-aware):
  - Compute today's RTH open (first bar with ET-min >= 9:30 on today's
    ET day) and prior trading day's RTH close (last bar before today
    whose ET-min is in [9:30, 16:00)).
  - Wait `wait_minutes` after RTH open before considering entries.
  - No new entries past `cutoff_et_min` (default 14:00 ET); at cutoff,
    close any open position.
  - Gap-up (gap >= min_gap) -> fade short, but only if current close
    has moved below today's open (showing reversal intent).
  - Gap-down (gap <= -min_gap) -> fade long, but only if current
    close has moved above today's open.
  - Exit when price reaches prior_close (gap filled).
"""
from __future__ import annotations

from app.services.market_clock import (
    RTH_CLOSE_ET_MIN,
    RTH_OPEN_ET_MIN,
    to_et,
)
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)

_DEFAULT_MIN_GAP_PTS = 5.0
_DEFAULT_WAIT_MINUTES = 15
_DEFAULT_CUTOFF_ET_MIN = 14 * 60
_WARMUP_BARS = 60


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


class GapFillStrategy:
    key: str = "gap_fill"
    name: str = "GapFill"
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
        min_gap = float(params.get("min_gap_pts", _DEFAULT_MIN_GAP_PTS))
        wait_min = int(params.get("wait_minutes", _DEFAULT_WAIT_MINUTES))
        cutoff = int(params.get("cutoff_et_min", _DEFAULT_CUTOFF_ET_MIN))

        carry = _position_sign(current_position)
        n = len(primary_bars)
        if n < _WARMUP_BARS:
            return StrategyResult(target=carry, meta={"phase": "warmup"})

        last_clock = to_et(primary_bars.index[-1])
        last_close = float(primary_bars["close"].iloc[-1])
        today = last_clock.day

        today_open: float | None = None
        prior_close: float | None = None
        prior_day: str | None = None
        for j in range(n - 1, -1, -1):
            clock = to_et(primary_bars.index[j])
            if (
                clock.day == today
                and clock.minutes >= RTH_OPEN_ET_MIN
                and today_open is None
            ):
                today_open = float(primary_bars["open"].iloc[j])
            if clock.day != today and RTH_OPEN_ET_MIN <= clock.minutes < RTH_CLOSE_ET_MIN:
                if prior_day is None:
                    prior_day = clock.day
                if clock.day == prior_day:
                    if prior_close is None:
                        prior_close = float(primary_bars["close"].iloc[j])
                elif prior_day is not None:
                    break

        if today_open is None or prior_close is None:
            return StrategyResult(target=0, meta={"phase": "no-gap-info"})

        gap = today_open - prior_close

        in_wait = last_clock.minutes < RTH_OPEN_ET_MIN + wait_min
        past_cutoff = last_clock.minutes >= cutoff
        if in_wait or past_cutoff:
            if carry != 0 and past_cutoff:
                return StrategyResult(
                    target=0,
                    meta={"phase": "eod-flat", "gap": gap, "close": last_close, "target_price": prior_close},
                )
            return StrategyResult(
                target=carry,
                meta={"phase": "wait", "gap": gap, "close": last_close},
            )

        if carry > 0:
            if last_close >= prior_close:
                return StrategyResult(
                    target=0,
                    meta={"phase": "gap-filled-long", "gap": gap, "target_price": prior_close, "close": last_close},
                )
            return StrategyResult(
                target=1,
                meta={"phase": "hold-long", "gap": gap, "target_price": prior_close, "close": last_close},
            )
        if carry < 0:
            if last_close <= prior_close:
                return StrategyResult(
                    target=0,
                    meta={"phase": "gap-filled-short", "gap": gap, "target_price": prior_close, "close": last_close},
                )
            return StrategyResult(
                target=-1,
                meta={"phase": "hold-short", "gap": gap, "target_price": prior_close, "close": last_close},
            )

        if gap >= min_gap and last_close < today_open:
            return StrategyResult(
                target=-1,
                meta={"phase": "enter-fade-gap-up", "gap": gap, "close": last_close, "target_price": prior_close},
            )
        if gap <= -min_gap and last_close > today_open:
            return StrategyResult(
                target=1,
                meta={"phase": "enter-fade-gap-down", "gap": gap, "close": last_close, "target_price": prior_close},
            )
        return StrategyResult(
            target=0,
            meta={"phase": "watching", "gap": gap, "close": last_close},
        )
