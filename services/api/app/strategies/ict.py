"""ICT strategy -- port of `ict` from the source Node bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies.js
        (function `ictStrategy`, registered as `STRATEGIES.ict`).

Behavior (single-timeframe; RTH-only; sweep + FVG confluence):
  - Offhours: target = 0 (force flat).
  - Holding (currentPos != 0): carry -- return current bias, phase=holding.
  - Flat & inside RTH:
      * Scan recent bars in [max(sweep_lookback, end - sweep_window), end]
        for liquidity sweeps:
          - Bear sweep at bar k: bar.high > swing_high (prior sweep_lookback)
            AND bar.close < swing_high AND upper_wick / range >= wick_ratio.
          - Bull sweep mirror.
      * Find recent unfilled FVG via `find_recent_fvg`.
      * Long if both a bull sweep AND price in bull FVG zone.
      * Short if both a bear sweep AND price in bear FVG zone.
"""
from __future__ import annotations

from app.services.market_clock import (
    RTH_CLOSE_ET_MIN,
    RTH_OPEN_ET_MIN,
    to_et,
)
from app.strategies._patterns import find_recent_fvg, find_swing_high_low
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
)

_DEFAULT_FVG_LOOKBACK = 20
_DEFAULT_SWEEP_LOOKBACK = 10
_DEFAULT_SWEEP_WINDOW = 5
_DEFAULT_WICK_RATIO = 0.5


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


class IctStrategy:
    key: str = "ict"
    name: str = "ICT"
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
        fvg_lookback = int(params.get("fvg_lookback", _DEFAULT_FVG_LOOKBACK))
        sweep_lookback = int(params.get("sweep_lookback", _DEFAULT_SWEEP_LOOKBACK))
        sweep_window = int(params.get("sweep_window", _DEFAULT_SWEEP_WINDOW))
        wick_ratio = float(params.get("wick_ratio", _DEFAULT_WICK_RATIO))

        carry = _position_sign(current_position)
        n = len(primary_bars)
        if n < max(fvg_lookback, sweep_lookback) + 3:
            return StrategyResult(target=carry, meta={"phase": "warmup"})

        last_clock = to_et(primary_bars.index[-1])
        if not (RTH_OPEN_ET_MIN <= last_clock.minutes < RTH_CLOSE_ET_MIN):
            return StrategyResult(target=0, meta={"phase": "offhours"})

        if carry != 0:
            return StrategyResult(target=carry, meta={"phase": "holding"})

        last_close = float(primary_bars["close"].iloc[-1])
        last_idx = n - 1
        highs = primary_bars["high"].astype(float).to_numpy()
        lows = primary_bars["low"].astype(float).to_numpy()
        opens = primary_bars["open"].astype(float).to_numpy()
        closes = primary_bars["close"].astype(float).to_numpy()

        recent_bull_sweep: dict[str, float | int] | None = None
        recent_bear_sweep: dict[str, float | int] | None = None
        scan_start = max(sweep_lookback, last_idx - sweep_window)
        for k in range(scan_start, last_idx + 1):
            swing_high, swing_low = find_swing_high_low(
                primary_bars, start_idx=k - sweep_lookback, end_idx=k
            )
            bar_range = highs[k] - lows[k]
            if bar_range <= 0:
                continue
            upper_wick = highs[k] - max(opens[k], closes[k])
            lower_wick = min(opens[k], closes[k]) - lows[k]
            if highs[k] > swing_high and closes[k] < swing_high and upper_wick / bar_range >= wick_ratio:
                recent_bear_sweep = {"bar_idx": k, "level": swing_high}
            if lows[k] < swing_low and closes[k] > swing_low and lower_wick / bar_range >= wick_ratio:
                recent_bull_sweep = {"bar_idx": k, "level": swing_low}

        fvg = find_recent_fvg(primary_bars, end_idx=last_idx, lookback=fvg_lookback)

        if recent_bull_sweep is not None and fvg.bull is not None:
            if fvg.bull.low <= last_close <= fvg.bull.high:
                return StrategyResult(
                    target=1,
                    meta={
                        "phase": "ict-long",
                        "sweep_bar": int(recent_bull_sweep["bar_idx"]),
                        "sweep_level": float(recent_bull_sweep["level"]),
                        "fvg_high": fvg.bull.high,
                        "fvg_low": fvg.bull.low,
                        "close": last_close,
                    },
                )
        if recent_bear_sweep is not None and fvg.bear is not None:
            if fvg.bear.low <= last_close <= fvg.bear.high:
                return StrategyResult(
                    target=-1,
                    meta={
                        "phase": "ict-short",
                        "sweep_bar": int(recent_bear_sweep["bar_idx"]),
                        "sweep_level": float(recent_bear_sweep["level"]),
                        "fvg_high": fvg.bear.high,
                        "fvg_low": fvg.bear.low,
                        "close": last_close,
                    },
                )

        return StrategyResult(target=0, meta={"phase": "no-confluence"})
