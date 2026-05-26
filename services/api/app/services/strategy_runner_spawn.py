"""Spawn one StrategyRunnerContext per ticker resolved from a watchlist.

Bridges Phase 5's universe input layer to Phase 4's per-ticker runner.
Owns:
  - Inserting one `strategy_runs` row per resolved ticker (status=pending,
    params={"watchlist_id": "<uuid>"}).
  - Emitting one `EVENT_UNIVERSE_RESOLVED` row per spawned context, BEFORE
    the runner loop emits its own `run_started`.
  - Constructing the `StrategyRunnerContext` per ticker.

Does NOT schedule the runners -- callers (the future Phase 8 CLI, the
Phase 5 acceptance test) decide when to `asyncio.gather(run(c) for c in
contexts)`.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAdapter
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEventLevel,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.llm_judge import JudgeLlmClient
from app.services.strategy_run_events import (
    EVENT_UNIVERSE_RESOLVED,
    emit_strategy_run_event,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.universe_resolver import resolve_watchlist_tickers
from app.strategies.base import Strategy, StrategyParams


async def spawn_contexts_from_watchlist(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    strategy: Strategy,
    mode: StrategyRunMode,
    params: StrategyParams,
    broker: BrokerAdapter,
    session_maker: Callable[[], AsyncSession],
    cancel_event_factory: Callable[[], asyncio.Event],
    llm_client: JudgeLlmClient,
    approval_poll_interval_seconds: float = 1.0,
    approval_paper_auto_approve_after_seconds: float = 0.0,
    approval_live_expires_after_seconds: float = 300.0,
) -> list[StrategyRunnerContext]:
    """Resolve the watchlist, insert one StrategyRun per ticker, return contexts.

    Raises EmptyUniverseError if the watchlist has zero members.
    Raises WatchlistNotFoundError if the watchlist doesn't exist.
    """
    tickers = await resolve_watchlist_tickers(session, watchlist_id)

    contexts: list[StrategyRunnerContext] = []
    for ticker in tickers:
        run_id = uuid.uuid4()
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key=strategy.key,
                ticker=ticker,
                mode=mode.value,
                status=StrategyRunStatus.pending.value,
                params={"watchlist_id": str(watchlist_id)},
            )
        )
        contexts.append(
            StrategyRunnerContext(
                run_id=run_id,
                strategy=strategy,
                ticker=ticker,
                mode=mode.value,
                params=params,
                broker=broker,
                session_maker=session_maker,
                cancel_event=cancel_event_factory(),
                llm_client=llm_client,
                approval_poll_interval_seconds=approval_poll_interval_seconds,
                approval_paper_auto_approve_after_seconds=approval_paper_auto_approve_after_seconds,
                approval_live_expires_after_seconds=approval_live_expires_after_seconds,
            )
        )
    await session.commit()

    async with session_maker() as event_session:
        for ctx in contexts:
            emit_strategy_run_event(
                event_session,
                run_id=ctx.run_id,
                event_kind=EVENT_UNIVERSE_RESOLVED,
                level=StrategyRunEventLevel.info,
                payload={
                    "watchlist_id": str(watchlist_id),
                    "resolved_tickers": list(tickers),
                    "ticker": ctx.ticker,
                },
            )
        await event_session.commit()

    return contexts


__all__ = ["spawn_contexts_from_watchlist"]
