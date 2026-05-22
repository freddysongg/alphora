"""Multi-bar pattern helpers used by ICT and Confluence-Long.

Ports `findRecentFVG` (from `/Users/freddy/conductor/workspaces/topStepx/
hanoi/lib/strategies.js`) and `_pivotLow` (from `lib/strategies/
confluence-long.js`). Bar-for-bar parity matters because the strategies
that consume these helpers are subject to bar-for-bar golden tests.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd  # type: ignore[import-untyped]


@dataclass(frozen=True)
class FvgZone:
    """A Fair Value Gap zone.

    `high` is the upper edge, `low` is the lower edge, `bar_idx` is the
    integer position in the input bars of the middle bar that "leaves"
    the gap. `kind` is "bull" or "bear".
    """

    kind: str
    high: float
    low: float
    bar_idx: int


@dataclass(frozen=True)
class FvgScanResult:
    bull: FvgZone | None
    bear: FvgZone | None


def find_recent_fvg(
    bars: pd.DataFrame, *, end_idx: int, lookback: int
) -> FvgScanResult:
    """Scan bars `[max(2, end_idx - lookback), end_idx)` for the most
    recent UNFILLED bullish and bearish FVGs.

    Bullish FVG: bar[j].low > bar[j-2].high and no later bar in
    `(j, end_idx)` has low <= bar[j-2].high.
    Bearish FVG: bar[j].high < bar[j-2].low and no later bar in
    `(j, end_idx)` has high >= bar[j-2].low.

    Mirrors `findRecentFVG` in `lib/strategies.js` exactly.
    """
    bull: FvgZone | None = None
    bear: FvgZone | None = None
    start = max(2, end_idx - lookback)
    highs = bars["high"].astype(float).to_numpy()
    lows = bars["low"].astype(float).to_numpy()
    for j in range(start, end_idx):
        if bull is None and lows[j] > highs[j - 2]:
            zone_high = float(lows[j])
            zone_low = float(highs[j - 2])
            filled = False
            for k in range(j + 1, end_idx):
                if lows[k] <= zone_low:
                    filled = True
                    break
            if not filled:
                bull = FvgZone(kind="bull", high=zone_high, low=zone_low, bar_idx=j)
        if bear is None and highs[j] < lows[j - 2]:
            zone_high = float(lows[j - 2])
            zone_low = float(highs[j])
            filled = False
            for k in range(j + 1, end_idx):
                if highs[k] >= zone_high:
                    filled = True
                    break
            if not filled:
                bear = FvgZone(kind="bear", high=zone_high, low=zone_low, bar_idx=j)
    return FvgScanResult(bull=bull, bear=bear)


def find_swing_high_low(
    bars: pd.DataFrame, *, start_idx: int, end_idx: int
) -> tuple[float, float]:
    """Return (max high, min low) across bars `[start_idx, end_idx)`."""
    highs = bars["high"].iloc[start_idx:end_idx].astype(float).to_numpy()
    lows = bars["low"].iloc[start_idx:end_idx].astype(float).to_numpy()
    return float(highs.max()), float(lows.min())


def pivot_low(
    bars: pd.DataFrame, *, end_idx: int, lookback: int, left: int, right: int
) -> float | None:
    """Scan back from `end_idx - right` to `max(left, end_idx - lookback)`
    for the most recent confirmed pivot low.

    A bar at index j is a pivot low iff `bars[k].low > bars[j].low` for
    every `k` in `[j - left, j + right]` with `k != j`. Returns the
    pivot low's price, or None.

    Mirrors `_pivotLow` in `lib/strategies/confluence-long.js` exactly.
    """
    lows = bars["low"].astype(float).to_numpy()
    scan_to = end_idx - right
    scan_from = max(left, end_idx - lookback)
    for j in range(scan_to, scan_from - 1, -1):
        ok = True
        for k in range(j - left, j + right + 1):
            if k == j:
                continue
            if k < 0 or k >= len(lows):
                ok = False
                break
            if lows[k] <= lows[j]:
                ok = False
                break
        if ok:
            return float(lows[j])
    return None


__all__ = [
    "FvgScanResult",
    "FvgZone",
    "find_recent_fvg",
    "find_swing_high_low",
    "pivot_low",
]
