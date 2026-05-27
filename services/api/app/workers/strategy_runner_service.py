"""Long-lived worker that runs ONE strategy runner against an env-var
configured (strategy_key, ticker, mode) tuple. This is the deliberate
stopgap until the Phase 8 `alphora-trade` CLI lands; multi-ticker /
multi-strategy fan-out is NOT in scope here.

Entry point:
    services/api/.venv/bin/python -m app.workers.strategy_runner_service

Required env (when STRATEGY_RUNNER_ENABLED=true):
    STRATEGY_KEY     one of the keys in app.strategies.STRATEGY_REGISTRY
    STRATEGY_TICKER  e.g. "SPY"
    STRATEGY_MODE    "paper" or "live"
    OPENAI_API_KEY   required for "live" mode; warn-only for "paper"
    ALPACA_API_KEY / ALPACA_API_SECRET / ALPACA_MODE  required by AlpacaAdapter.from_env

Spawn path mirrors `app.scripts.smoke_paper_run`: we create (or reuse) a
single-member watchlist named `runner-<strategy_key>-<ticker>` and delegate
to `spawn_contexts_from_watchlist`, which inserts the `strategy_runs` FK
row and emits the `universe_resolved` event before the runner loop starts.
Constructing `StrategyRunnerContext` directly and calling `runner_run`
without that row would FK-violate on the first event insert.

Carry-forward limitation: `_portfolio_snapshot` in `strategy_runner.py`
sees only the current ticker's local state and daily P&L is hardcoded
zero, so multi-ticker live caps cannot enforce portfolio-level halts.
This service is SAFE for single-ticker paper and single-ticker live with
tight caps; we log a WARNING in live mode to make that visible.
"""
from __future__ import annotations

import asyncio
import signal
import uuid
from typing import Literal

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.alpaca import AlpacaAdapter
from app.config import get_settings
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.db.models_strategy_runner import StrategyRunMode
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.schemas.budget import BudgetThresholds
from app.services.budget import BudgetGuard
from app.services.llm.client import LlmClient
from app.services.strategy_runner import run as runner_run
from app.services.strategy_runner_spawn import spawn_contexts_from_watchlist
from app.strategies import STRATEGY_REGISTRY

_RUNNER_WATCHLIST_PREFIX = "runner-"

_logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    if not settings.strategy_runner_enabled:
        _logger.info("strategy_runner_service_disabled")
        return

    if not settings.strategy_key:
        raise RuntimeError(
            "STRATEGY_KEY must be set when STRATEGY_RUNNER_ENABLED=true"
        )
    if not settings.strategy_ticker:
        raise RuntimeError(
            "STRATEGY_TICKER must be set when STRATEGY_RUNNER_ENABLED=true"
        )

    strategy_cls = STRATEGY_REGISTRY[settings.strategy_key]
    mode: Literal["paper", "live"] = settings.strategy_mode
    ticker = settings.strategy_ticker

    if mode == "live" and not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY must be set for live mode; refusing to start"
        )
    if mode == "paper" and not settings.openai_api_key:
        _logger.warning(
            "strategy_runner_service_paper_no_openai_key",
            note=(
                "judge will conservative-default-veto every signal; orders "
                "still submit"
            ),
        )
    if mode == "live":
        _logger.warning(
            "strategy_runner_service_live_single_ticker_only",
            note=(
                "_portfolio_snapshot sees only current ticker; multi-ticker "
                "live caps cannot enforce portfolio-level halts; keep caps "
                "tight and run one ticker per service"
            ),
        )

    strategy = strategy_cls()
    broker = AlpacaAdapter.from_env()

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    thresholds = BudgetThresholds(
        per_stage_usd=settings.per_stage_budget_caps_usd
    )
    budget_guard = BudgetGuard(thresholds=thresholds)
    llm_client = LlmClient(
        openai_client=openai_client, budget_guard=budget_guard
    )

    cancel_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, cancel_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: cancel_event.set())

    watchlist_id = await _ensure_runner_watchlist(
        strategy_key=strategy.key, ticker=ticker
    )

    strategy_run_mode = (
        StrategyRunMode.paper if mode == "paper" else StrategyRunMode.live
    )

    async with default_session_factory() as spawn_session:
        contexts = await spawn_contexts_from_watchlist(
            spawn_session,
            watchlist_id=watchlist_id,
            strategy=strategy,
            mode=strategy_run_mode,
            params={},
            broker=broker,
            session_maker=default_session_factory,
            cancel_event_factory=lambda: cancel_event,
            llm_client=llm_client,
        )

    if len(contexts) != 1:
        raise RuntimeError(
            f"expected exactly 1 spawned context for ticker={ticker}, "
            f"got {len(contexts)}"
        )
    runner_context = contexts[0]

    _logger.info(
        "strategy_runner_service_started",
        run_id=str(runner_context.run_id),
        strategy_key=strategy.key,
        ticker=ticker,
        mode=mode,
    )
    try:
        await runner_run(runner_context)
    finally:
        _logger.info(
            "strategy_runner_service_stopped",
            run_id=str(runner_context.run_id),
        )


async def _ensure_runner_watchlist(
    *, strategy_key: str, ticker: str
) -> uuid.UUID:
    """Reuse or create a transient one-member watchlist for the runner.

    Idempotent on the `runner-<strategy_key>-<ticker>` name so service
    restarts do not duplicate rows. Mirrors `_ensure_demo_watchlist` in
    `app.scripts.smoke_paper_run`.
    """
    name = f"{_RUNNER_WATCHLIST_PREFIX}{strategy_key}-{ticker}"
    async with default_session_factory() as session:
        existing_id = await _find_watchlist_id_by_name(session, name=name)
        if existing_id is not None:
            return existing_id
        watchlist = Watchlist(
            id=uuid.uuid4(),
            name=name,
            source=WatchlistSource.manual.value,
            is_active=True,
        )
        session.add(watchlist)
        await session.flush()
        session.add(
            WatchlistMember(
                id=uuid.uuid4(),
                watchlist_id=watchlist.id,
                ticker=ticker,
            )
        )
        await session.commit()
        return watchlist.id


async def _find_watchlist_id_by_name(
    session: AsyncSession, *, name: str
) -> uuid.UUID | None:
    row = (
        await session.execute(select(Watchlist).where(Watchlist.name == name))
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.id


if __name__ == "__main__":
    main()


__all__ = ["main"]
