"""Strategy runner (spec section 6.4) -- Phase 4 implementation.

One async task per (strategy_key, ticker, mode) tuple. Consumes a real-
time bar stream from a broker adapter; evaluates the strategy per bar;
routes signals through risk-caps -> llm_judge -> approval_queue -> broker.
Updates ATR-based trailing stops between bars. Persists every decision
to `strategy_run_events`.

Task 14 lands the skeleton only: bar consumption, indicator window
append, evaluate-event emission, lifecycle status transitions, and
cancel-event honoring. Order submission (Task 16), position adoption
(Task 15), trail updates (Task 17), and EOD flatten (Task 18) extend
this in subsequent tasks.

This file is the runner orchestrator only. All pure logic (risk caps,
trail manager, indicator window, judge stub, approval stub) lives in
sibling modules. The runner is the ONLY module that imports both the
broker adapter and the DB session.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Bar, BrokerAdapter
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEventLevel,
    StrategyRunStatus,
)
from app.services.strategy_indicator_window import (
    INDICATOR_WINDOW_BARS,
    BoundedBarBuffer,
)
from app.services.strategy_run_events import (
    EVENT_EVALUATE,
    EVENT_RUN_STARTED,
    EVENT_RUN_STOPPED,
    emit_strategy_run_event,
)
from app.services.trail_manager import TrailState
from app.strategies.base import Strategy, StrategyParams, StrategyResult


@dataclass
class StrategyRunnerContext:
    """Runtime container for one runner.

    `session_maker` is a callable returning a fresh AsyncSession per
    invocation (the runner opens a new session per bar to bound the
    transaction lifetime). `cancel_event` is the runner's only
    cooperative-stop signal -- set it from outside to wind down.
    `current_position` is the runner's authoritative view of the open
    share count (positive = long, negative = short). Task 15 wires
    position adoption to seed this from broker.get_positions().
    """

    run_id: uuid.UUID
    strategy: Strategy
    ticker: str
    mode: Literal["paper", "live"]
    params: StrategyParams
    broker: BrokerAdapter
    session_maker: Callable[[], AsyncSession]
    cancel_event: asyncio.Event
    indicator_window: BoundedBarBuffer = field(
        default_factory=lambda: BoundedBarBuffer(max_size=INDICATOR_WINDOW_BARS)
    )
    current_position: Decimal = field(default_factory=lambda: Decimal("0"))
    trail_state: TrailState | None = None
    last_exit_bar_ts: datetime | None = None
    orders_in_last_minute: list[datetime] = field(default_factory=list)


async def run(ctx: StrategyRunnerContext) -> None:
    """Main loop. Runs until `ctx.cancel_event` is set or the bar stream
    completes (whichever comes first). Always writes a run_started event
    on entry and a run_stopped event on exit, and updates the
    `strategy_runs` row's status + stopped_at."""
    await _mark_status(ctx, StrategyRunStatus.running, started=True)
    await _emit_event(
        ctx,
        kind=EVENT_RUN_STARTED,
        level=StrategyRunEventLevel.info,
        payload={
            "strategy_key": ctx.strategy.key,
            "ticker": ctx.ticker,
            "mode": ctx.mode,
        },
    )

    iterator = ctx.broker.stream_bars([ctx.ticker], ctx.strategy.primary_timeframe)

    try:
        async for bar in iterator:
            if ctx.cancel_event.is_set():
                break
            await _process_bar(ctx, bar)
    except asyncio.CancelledError:
        pass
    finally:
        await _emit_event(
            ctx,
            kind=EVENT_RUN_STOPPED,
            level=StrategyRunEventLevel.info,
            payload={"reason": "cancel" if ctx.cancel_event.is_set() else "stream_end"},
        )
        await _mark_status(ctx, StrategyRunStatus.stopped, stopped=True)


async def _process_bar(ctx: StrategyRunnerContext, bar: Bar) -> None:
    """Append bar, call evaluate, emit evaluate event.

    Order submission, trail updates, and EOD logic land in later tasks.
    """
    ctx.indicator_window.append(bar)
    primary = ctx.indicator_window.to_frame()
    result: StrategyResult = ctx.strategy.evaluate(
        primary_bars=primary,
        secondary_bars={},
        current_position=int(ctx.current_position),
        params=ctx.params,
    )
    await _emit_event(
        ctx,
        kind=EVENT_EVALUATE,
        level=StrategyRunEventLevel.info,
        payload={
            "target": result.target,
            "stop_pts": result.stop_pts,
            "size_hint": result.size_hint,
            "meta": result.meta,
        },
        bar_ts=bar.as_of,
    )


async def _emit_event(
    ctx: StrategyRunnerContext,
    *,
    kind: str,
    level: StrategyRunEventLevel,
    payload: dict[str, object],
    bar_ts: datetime | None = None,
) -> None:
    async with ctx.session_maker() as session:
        emit_strategy_run_event(
            session,
            run_id=ctx.run_id,
            event_kind=kind,
            level=level,
            payload=payload,
            bar_ts=bar_ts,
        )
        await session.commit()


async def _mark_status(
    ctx: StrategyRunnerContext,
    status: StrategyRunStatus,
    *,
    started: bool = False,
    stopped: bool = False,
) -> None:
    values: dict[str, object] = {"status": status.value}
    if started:
        values["started_at"] = datetime.now(UTC)
    if stopped:
        values["stopped_at"] = datetime.now(UTC)
    async with ctx.session_maker() as session:
        await session.execute(
            update(StrategyRun).where(StrategyRun.id == ctx.run_id).values(**values)
        )
        await session.commit()


__all__ = ["StrategyRunnerContext", "run"]
