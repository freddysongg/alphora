"""Strategy Protocol + supporting types (spec §6.1).

`Bars` is a pandas DataFrame with columns `open`, `high`, `low`, `close`,
`volume` and a UTC `DatetimeIndex`. `StrategyParams` is a flat dict of
scalar params. `Timeframe` is re-exported from `app.brokers.base` to
avoid duplicating the literal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeAlias

import pandas as pd  # type: ignore[import-untyped]

from app.brokers.base import Timeframe

Bars: TypeAlias = pd.DataFrame
StrategyParams: TypeAlias = dict[str, float | int | bool | str]


@dataclass(frozen=True)
class TrailSpec:
    """ATR-based trailing-stop spec.

    The strategy returns this in `StrategyResult.trail`; the runner
    (Phase 4) computes ATR each bar and recomputes the stop. Phase 1
    strategies do not return a trail (the MACD+RSI+ADX port leaves it
    None — pure entry/exit signal).
    """

    atr_multiplier: float
    atr_period: int = 14


@dataclass(frozen=True)
class StrategyResult:
    """Per-bar evaluation result.

    `target` is the desired *bias* in {-1, 0, +1}, not a share count.
    The runner translates bias → share count using risk caps and size
    hints. `meta` carries strategy-specific diagnostics that the
    audit log and UI render verbatim.
    """

    target: int  # Literal[-1, 0, 1] — narrower than int but pandas/runtime ergonomics keep int
    meta: dict[str, float | str]
    size_hint: int | None = None
    stop_pts: float | None = None
    target_pts: float | None = None
    trail: TrailSpec | None = None


class Strategy(Protocol):
    """Per-strategy contract (spec §6.1).

    Implementations expose static metadata as class attributes and a
    pure `evaluate` method. `evaluate` is called once per bar with the
    full primary-tf history up to "now" (no peeking — the runner only
    passes closed bars).
    """

    key: str
    name: str
    primary_timeframe: Timeframe
    secondary_timeframes: list[Timeframe]
    requires_rth: bool

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult: ...


# Silence the unused-import linter on `field`; reserved for forward
# compatibility when concrete strategies declare per-strategy param
# defaults via dataclass `field(default_factory=...)`.
_ = field

__all__ = [
    "Bars",
    "Strategy",
    "StrategyParams",
    "StrategyResult",
    "Timeframe",
    "TrailSpec",
]
