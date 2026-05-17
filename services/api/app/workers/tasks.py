import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db.models_runs import ResearchRun, Strategy
from app.db.session import session_factory
from app.services.run_orchestrator import RunOrchestrator
from app.trading_agents.adapter import TradingAgentsAdapter


def execute_research_run(run_id_hex: str) -> None:
    """RQ task entrypoint for executing a single research run.

    Bridges sync RQ to the async orchestrator via asyncio.run. RQ pickles tasks
    by their fully-qualified import path so this function must remain importable
    as `app.workers.tasks.execute_research_run`.

    Dispatches on the run's strategy. funnel_research is reserved for a later
    phase and currently fails the run rather than silently routing it to the
    TradingAgents adapter.
    """
    run_id = UUID(run_id_hex)
    asyncio.run(_dispatch(run_id))


async def _dispatch(run_id: UUID) -> None:
    strategy = await _load_strategy(run_id)
    adapter = TradingAgentsAdapter()
    orchestrator = RunOrchestrator(session_factory=session_factory, adapter=adapter)
    if strategy != Strategy.tradingagents.value:
        await orchestrator.fail(
            run_id,
            f"strategy {strategy!r} is not implemented yet (planned for Phase 4+)",
        )
        return
    await orchestrator.execute(run_id)


async def _load_strategy(run_id: UUID) -> str:
    async with session_factory() as session:
        result = await session.execute(
            select(ResearchRun.strategy).where(ResearchRun.id == run_id)
        )
        return result.scalar_one()
