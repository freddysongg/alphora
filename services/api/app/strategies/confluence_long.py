"""Confluence-Long strategy -- port of `confluence-long` from the source bot.

Source: /Users/freddy/conductor/workspaces/topStepx/hanoi/lib/strategies/
        confluence-long.js (function `confluenceLongStrategy`).

Behavior (multi-timeframe: 1min primary + 5min secondary; long-only):
  Entry (flat) requires ALL three on the same 1-min bar close:
    1. EMA(8) crosses above EMA(21).
    2. MACD(8, 17, 9) crossed above signal below `macd_threshold` (-3)
       within the last `lookback` bars.
    3. ADX(14) on 5-min bars >= `adx_min` (15).
  Position sizing in the source bot uses `targetRiskDollars` /
  `pointValue` math; we ignore sizing here (Phase 3 backtests use the
  engine's fixed `position_size_shares=1`) and instead emit the
  recommended size hint via `meta.entry_size`.
  Carry: target = current bias; updated trail thresholds in meta.
  TrailSpec: when 5min ATR is defined, returns
  `TrailSpec(atr_multiplier=trail_distance_atr, atr_period=atr_period)`.
"""
from __future__ import annotations

import math

import pandas as pd  # type: ignore[import-untyped]

from app.indicators import adx, atr, ema, macd
from app.strategies._patterns import pivot_low
from app.strategies.base import (
    Bars,
    StrategyParams,
    StrategyResult,
    Timeframe,
    TrailSpec,
)

_DEFAULT_LOOKBACK = 12
_DEFAULT_MACD_FAST = 8
_DEFAULT_MACD_SLOW = 17
_DEFAULT_MACD_SIGNAL = 9
_DEFAULT_MACD_THRESHOLD = -3.0
_DEFAULT_ADX_MIN = 15.0
_DEFAULT_ADX_LENGTH = 14
_DEFAULT_PIVOT_LOOKBACK = 12
_DEFAULT_PIVOT_LEFT = 2
_DEFAULT_PIVOT_RIGHT = 2
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_BREAK_EVEN_ATR = 1.0
_DEFAULT_TRAIL_TRIGGER_ATR = 1.5
_DEFAULT_TRAIL_DISTANCE_ATR = 0.5


def _position_sign(current_position: int) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


def _atr_thresholds(
    bars_5m: pd.DataFrame,
    *,
    period: int,
    be_atr: float,
    tt_atr: float,
    td_atr: float,
) -> dict[str, float]:
    if len(bars_5m) < period + 2:
        return {}
    atr_series = atr(bars_5m, period=period)
    atr_now = float(atr_series.iloc[-1])
    if math.isnan(atr_now):
        return {}
    return {
        "atr_5min": round(atr_now, 2),
        "break_even_pts": round(atr_now * be_atr, 2),
        "trail_trigger_pts": round(atr_now * tt_atr, 2),
        "trail_distance_pts": round(atr_now * td_atr, 2),
        "break_even_atr_multiplier": be_atr,
        "trail_trigger_atr_multiplier": tt_atr,
        "trail_distance_atr_multiplier": td_atr,
    }


class ConfluenceLongStrategy:
    key: str = "confluence_long"
    name: str = "Confluence-Long"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = ["5min"]  # noqa: RUF012
    requires_rth: bool = False

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
        m_fast = int(params.get("macd_fast", _DEFAULT_MACD_FAST))
        m_slow = int(params.get("macd_slow", _DEFAULT_MACD_SLOW))
        m_sig = int(params.get("macd_signal", _DEFAULT_MACD_SIGNAL))
        threshold = float(params.get("macd_threshold", _DEFAULT_MACD_THRESHOLD))
        adx_min = float(params.get("adx_min", _DEFAULT_ADX_MIN))
        adx_len = int(params.get("adx_length", _DEFAULT_ADX_LENGTH))
        piv_lookback = int(params.get("pivot_lookback", _DEFAULT_PIVOT_LOOKBACK))
        piv_left = int(params.get("pivot_left", _DEFAULT_PIVOT_LEFT))
        piv_right = int(params.get("pivot_right", _DEFAULT_PIVOT_RIGHT))
        atr_period = int(params.get("atr_period", _DEFAULT_ATR_PERIOD))
        be_atr = float(params.get("break_even_atr", _DEFAULT_BREAK_EVEN_ATR))
        tt_atr = float(params.get("trail_trigger_atr", _DEFAULT_TRAIL_TRIGGER_ATR))
        td_atr = float(params.get("trail_distance_atr", _DEFAULT_TRAIL_DISTANCE_ATR))

        bars_5m = secondary_bars.get("5min")
        if bars_5m is None:
            bars_5m = pd.DataFrame(
                {col: [] for col in ["open", "high", "low", "close", "volume"]}
            )

        trail_thresholds = _atr_thresholds(
            bars_5m,
            period=atr_period,
            be_atr=be_atr,
            tt_atr=tt_atr,
            td_atr=td_atr,
        )
        trail = (
            TrailSpec(atr_multiplier=td_atr, atr_period=atr_period)
            if trail_thresholds
            else None
        )

        carry = _position_sign(current_position)
        need = m_slow + m_sig + lookback + 5
        if len(primary_bars) < need:
            return StrategyResult(
                target=carry,
                meta={"phase": "warmup", **trail_thresholds},
                trail=trail,
            )

        if carry != 0:
            return StrategyResult(
                target=carry,
                meta={"phase": "holding", "entry_size": abs(current_position), **trail_thresholds},
                trail=trail,
            )

        closes = primary_bars["close"]
        i = len(closes) - 1

        e8 = ema(closes, period=8)
        e21 = ema(closes, period=21)
        e8_now = float(e8.iloc[i])
        e8_prev = float(e8.iloc[i - 1])
        e21_now = float(e21.iloc[i])
        e21_prev = float(e21.iloc[i - 1])
        if any(math.isnan(v) for v in (e8_now, e8_prev, e21_now, e21_prev)):
            return StrategyResult(
                target=0,
                meta={"phase": "warmup-ema", **trail_thresholds},
                trail=trail,
            )
        if not (e8_prev <= e21_prev and e8_now > e21_now):
            return StrategyResult(
                target=0,
                meta={
                    "phase": "no-ema-cross",
                    "ema_8": e8_now,
                    "ema_21": e21_now,
                    **trail_thresholds,
                },
                trail=trail,
            )

        macd_line, signal_line, _ = macd(closes, fast=m_fast, slow=m_slow, signal=m_sig)
        crossed_recently = False
        for k in range(i, max(0, i - lookback + 1) - 1, -1):
            if k < 1:
                break
            mk, mk_prev = float(macd_line.iloc[k]), float(macd_line.iloc[k - 1])
            sk, sk_prev = float(signal_line.iloc[k]), float(signal_line.iloc[k - 1])
            if any(math.isnan(v) for v in (mk, mk_prev, sk, sk_prev)):
                continue
            if mk_prev <= sk_prev and mk > sk and mk < threshold:
                crossed_recently = True
                break
        if not crossed_recently:
            return StrategyResult(
                target=0,
                meta={
                    "phase": "no-macd-setup",
                    "ema_8": e8_now,
                    "ema_21": e21_now,
                    "macd": float(macd_line.iloc[i]),
                    "signal": float(signal_line.iloc[i]),
                    **trail_thresholds,
                },
                trail=trail,
            )

        if len(bars_5m) <= adx_len * 2 + 2:
            return StrategyResult(
                target=0,
                meta={
                    "phase": "warmup-adx",
                    "ema_8": e8_now,
                    "ema_21": e21_now,
                    **trail_thresholds,
                },
                trail=trail,
            )
        adx_series = adx(bars_5m, period=adx_len)
        adx_val = float(adx_series.iloc[-1])
        if math.isnan(adx_val):
            return StrategyResult(
                target=0,
                meta={
                    "phase": "warmup-adx",
                    "ema_8": e8_now,
                    "ema_21": e21_now,
                    **trail_thresholds,
                },
                trail=trail,
            )
        if adx_val < adx_min:
            return StrategyResult(
                target=0,
                meta={
                    "phase": "adx-too-low",
                    "adx": adx_val,
                    "ema_8": e8_now,
                    "ema_21": e21_now,
                    **trail_thresholds,
                },
                trail=trail,
            )

        pivot_lo = pivot_low(
            primary_bars,
            end_idx=i,
            lookback=piv_lookback,
            left=piv_left,
            right=piv_right,
        )
        entry_price = float(closes.iloc[i])
        stop_pts = (
            round(entry_price - pivot_lo, 2)
            if pivot_lo is not None and pivot_lo < entry_price
            else 30.0
        )

        return StrategyResult(
            target=1,
            meta={
                "phase": "pivot" if pivot_lo else "fallback-stop",
                "ema_8": e8_now,
                "ema_21": e21_now,
                "macd": float(macd_line.iloc[i]),
                "signal": float(signal_line.iloc[i]),
                "adx": adx_val,
                "pivot_low": float(pivot_lo) if pivot_lo is not None else 0.0,
                "stop_pts": stop_pts,
                **trail_thresholds,
            },
            trail=trail,
            stop_pts=stop_pts,
        )
