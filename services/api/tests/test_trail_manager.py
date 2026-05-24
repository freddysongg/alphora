from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.brokers.base import Bar
from app.services.trail_manager import (
    TrailExit,
    TrailMode,
    TrailState,
    update_trail,
)
from app.strategies.base import TrailSpec


def _bar(*, high: float, low: float, close: float) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )


def _long_initial_state(entry: float = 100.0, stop: float = 98.0) -> TrailState:
    return TrailState(
        side="long",
        entry_price=Decimal(str(entry)),
        high_watermark=Decimal(str(entry)),
        low_watermark=Decimal(str(entry)),
        current_stop=Decimal(str(stop)),
        mode=TrailMode.initial,
    )


def _trail_spec() -> TrailSpec:
    return TrailSpec(atr_multiplier=0.5, atr_period=14)


def _meta(
    *,
    break_even_pts: float = 1.0,
    trail_trigger_pts: float = 1.5,
    trail_distance_pts: float = 0.5,
) -> dict[str, float | str]:
    return {
        "break_even_pts": break_even_pts,
        "trail_trigger_pts": trail_trigger_pts,
        "trail_distance_pts": trail_distance_pts,
    }


def test_initial_long_with_no_movement_stays_initial() -> None:
    state = _long_initial_state()
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=100.2, low=99.9, close=100.0),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.initial
    assert new_state.current_stop == Decimal("98.0")
    assert exit_signal is None


def test_long_promotes_to_break_even_when_high_minus_entry_passes_break_even_pts() -> None:
    state = _long_initial_state(entry=100.0, stop=98.0)
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=101.5, low=100.0, close=101.0),
        trail_spec=_trail_spec(),
        meta=_meta(break_even_pts=1.0),
    )
    assert new_state.mode == TrailMode.break_even
    assert new_state.current_stop == Decimal("100.0")
    assert exit_signal is None


def test_long_promotes_to_trailing_when_high_minus_entry_passes_trail_trigger_pts() -> None:
    state = TrailState(
        side="long",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("101.2"),
        low_watermark=Decimal("100.0"),
        current_stop=Decimal("100.0"),
        mode=TrailMode.break_even,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=101.7, low=101.0, close=101.5),
        trail_spec=_trail_spec(),
        meta=_meta(trail_trigger_pts=1.5, trail_distance_pts=0.5),
    )
    assert new_state.mode == TrailMode.trailing
    assert new_state.current_stop == Decimal("101.2")
    assert exit_signal is None


def test_long_trailing_stop_only_tightens_never_loosens() -> None:
    state = TrailState(
        side="long",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("102.0"),
        low_watermark=Decimal("100.0"),
        current_stop=Decimal("101.5"),
        mode=TrailMode.trailing,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=101.8, low=101.5, close=101.7),
        trail_spec=_trail_spec(),
        meta=_meta(trail_distance_pts=0.5),
    )
    assert new_state.high_watermark == Decimal("102.0")
    assert new_state.current_stop == Decimal("101.5")
    assert exit_signal is None


def test_long_exits_when_low_pierces_current_stop() -> None:
    state = TrailState(
        side="long",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("102.0"),
        low_watermark=Decimal("100.0"),
        current_stop=Decimal("101.5"),
        mode=TrailMode.trailing,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=101.6, low=101.4, close=101.4),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.stopped
    assert exit_signal is not None
    assert exit_signal.reason == "trail"
    assert exit_signal.exit_price == Decimal("101.5")


def test_long_exits_via_break_even_stop_when_low_pierces_entry() -> None:
    state = TrailState(
        side="long",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("101.2"),
        low_watermark=Decimal("100.0"),
        current_stop=Decimal("100.0"),
        mode=TrailMode.break_even,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=100.1, low=99.95, close=99.95),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.stopped
    assert exit_signal is not None
    assert exit_signal.reason == "break_even"


def test_long_exits_via_initial_stop_when_low_pierces_initial() -> None:
    state = _long_initial_state(entry=100.0, stop=98.0)
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=99.5, low=97.8, close=97.8),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.stopped
    assert exit_signal is not None
    assert exit_signal.reason == "stop"


def test_short_uses_inverted_thresholds() -> None:
    """For a short position, low_watermark instead of high_watermark; the
    exit is on a price RISING past the stop, not falling."""
    state = TrailState(
        side="short",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("100.0"),
        low_watermark=Decimal("100.0"),
        current_stop=Decimal("102.0"),
        mode=TrailMode.initial,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=99.5, low=98.4, close=98.5),
        trail_spec=_trail_spec(),
        meta=_meta(break_even_pts=1.0),
    )
    assert new_state.mode == TrailMode.break_even
    assert new_state.current_stop == Decimal("100.0")
    assert exit_signal is None


def test_short_exits_when_high_pierces_current_stop() -> None:
    state = TrailState(
        side="short",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("100.0"),
        low_watermark=Decimal("98.0"),
        current_stop=Decimal("98.5"),
        mode=TrailMode.trailing,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=98.6, low=98.3, close=98.5),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.stopped
    assert exit_signal is not None
    assert exit_signal.reason == "trail"


def test_trail_meta_missing_thresholds_returns_state_unchanged_no_exit() -> None:
    """If the strategy didn't emit break_even_pts / trail_*_pts in meta,
    the trail manager is a no-op (the position still has the initial
    stop the runner set up — entry minus stop_pts from StrategyResult)."""
    state = _long_initial_state()
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=101.5, low=99.9, close=101.0),
        trail_spec=_trail_spec(),
        meta={},
    )
    assert new_state.mode == TrailMode.initial
    assert exit_signal is None


@pytest.mark.parametrize("mode", [TrailMode.stopped])
def test_stopped_state_is_idempotent(mode: TrailMode) -> None:
    """Once stopped, subsequent bars must not re-fire exit signals."""
    state = TrailState(
        side="long",
        entry_price=Decimal("100.0"),
        high_watermark=Decimal("101.0"),
        low_watermark=Decimal("99.0"),
        current_stop=Decimal("99.5"),
        mode=mode,
    )
    new_state, exit_signal = update_trail(
        state=state,
        bar=_bar(high=99.0, low=98.0, close=98.5),
        trail_spec=_trail_spec(),
        meta=_meta(),
    )
    assert new_state.mode == TrailMode.stopped
    assert exit_signal is None


_ = TrailExit
