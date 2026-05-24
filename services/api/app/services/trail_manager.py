"""Dynamic position management (spec section 6.4, Phase 4 work item #3).

Pure function. The runner calls `update_trail(state, bar, trail_spec,
meta) -> (new_state, exit_signal)` once per bar for each open position.

Mode transitions:
  initial -> break_even   (when high/low passes meta.break_even_pts)
  break_even -> trailing  (when high/low passes meta.trail_trigger_pts)
  trailing -> trailing    (re-tighten on new watermark)
  any -> stopped          (when bar pierces current_stop)
  stopped -> stopped      (idempotent)

For a LONG position, "passes" means the new high - entry exceeds
threshold. For a SHORT position, "passes" means entry - new low
exceeds threshold. Stop direction inverts accordingly.

`exit_signal` is `None` while the position carries; on stop hit it's
a `TrailExit(reason, exit_price)`. Exit price is the stop price (not
the bar's low/high), matching standard stop-loss execution semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Literal

from app.brokers.base import Bar
from app.strategies.base import TrailSpec

TrailExitReason = Literal["stop", "break_even", "trail"]


class TrailMode(Enum):
    initial = "initial"
    break_even = "break_even"
    trailing = "trailing"
    stopped = "stopped"


@dataclass(frozen=True)
class TrailState:
    """Per-open-position snapshot. The runner persists this between
    bars (in-memory; not DB-backed in Phase 4)."""

    side: Literal["long", "short"]
    entry_price: Decimal
    high_watermark: Decimal
    low_watermark: Decimal
    current_stop: Decimal
    mode: TrailMode


@dataclass(frozen=True)
class TrailExit:
    reason: TrailExitReason
    exit_price: Decimal


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def update_trail(
    *,
    state: TrailState,
    bar: Bar,
    trail_spec: TrailSpec,
    meta: dict[str, float | str],
) -> tuple[TrailState, TrailExit | None]:
    """Return updated state + optional exit signal.

    `trail_spec` is a marker that the strategy wants a dynamic trail;
    meta carries the dollar-point thresholds the runner consumes:
    `break_even_pts`, `trail_trigger_pts`, `trail_distance_pts`. When
    these are missing (e.g., strategy returned bare `TrailSpec` without
    meta thresholds) the manager is a no-op.
    """
    _ = trail_spec

    if state.mode is TrailMode.stopped:
        return state, None

    high = _dec(bar.high)
    low = _dec(bar.low)

    new_high_wm = max(state.high_watermark, high)
    new_low_wm = min(state.low_watermark, low)

    if state.side == "long" and low < state.current_stop:
        return (
            replace(
                state,
                high_watermark=new_high_wm,
                low_watermark=new_low_wm,
                mode=TrailMode.stopped,
            ),
            TrailExit(reason=_exit_reason_for(state.mode), exit_price=state.current_stop),
        )
    if state.side == "short" and high > state.current_stop:
        return (
            replace(
                state,
                high_watermark=new_high_wm,
                low_watermark=new_low_wm,
                mode=TrailMode.stopped,
            ),
            TrailExit(reason=_exit_reason_for(state.mode), exit_price=state.current_stop),
        )

    break_even_pts = _meta_float(meta, "break_even_pts")
    trail_trigger_pts = _meta_float(meta, "trail_trigger_pts")
    trail_distance_pts = _meta_float(meta, "trail_distance_pts")
    if break_even_pts is None or trail_trigger_pts is None or trail_distance_pts is None:
        return (
            replace(state, high_watermark=new_high_wm, low_watermark=new_low_wm),
            None,
        )

    if state.side == "long":
        excursion = new_high_wm - state.entry_price
    else:
        excursion = state.entry_price - new_low_wm

    new_mode = state.mode
    new_stop = state.current_stop

    if state.mode is TrailMode.initial and excursion >= Decimal(str(break_even_pts)):
        new_mode = TrailMode.break_even
        new_stop = state.entry_price
    elif state.mode is TrailMode.break_even and excursion >= Decimal(str(trail_trigger_pts)):
        new_mode = TrailMode.trailing
        if state.side == "long":
            new_stop = new_high_wm - Decimal(str(trail_distance_pts))
        else:
            new_stop = new_low_wm + Decimal(str(trail_distance_pts))

    if new_mode is TrailMode.trailing:
        if state.side == "long":
            candidate = new_high_wm - Decimal(str(trail_distance_pts))
            if candidate > new_stop:
                new_stop = candidate
        else:
            candidate = new_low_wm + Decimal(str(trail_distance_pts))
            if candidate < new_stop:
                new_stop = candidate

    return (
        TrailState(
            side=state.side,
            entry_price=state.entry_price,
            high_watermark=new_high_wm,
            low_watermark=new_low_wm,
            current_stop=new_stop,
            mode=new_mode,
        ),
        None,
    )


def _exit_reason_for(mode: TrailMode) -> TrailExitReason:
    if mode is TrailMode.trailing:
        return "trail"
    if mode is TrailMode.break_even:
        return "break_even"
    return "stop"


def _meta_float(meta: dict[str, float | str], key: str) -> float | None:
    value = meta.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = [
    "TrailExit",
    "TrailExitReason",
    "TrailMode",
    "TrailState",
    "update_trail",
]
