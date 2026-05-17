import asyncio
from uuid import UUID

from app.db.session import session_factory
from app.services.run_orchestrator import RunOrchestrator
from app.trading_agents.adapter import TradingAgentsAdapter


def execute_research_run(run_id_hex: str) -> None:
    """RQ task entrypoint for executing a single research run.

    Bridges sync RQ to the async orchestrator via asyncio.run. RQ pickles tasks
    by their fully-qualified import path so this function must remain importable
    as `app.workers.tasks.execute_research_run`.
    """
    run_id = UUID(run_id_hex)
    adapter = TradingAgentsAdapter()
    orchestrator = RunOrchestrator(session_factory=session_factory, adapter=adapter)
    asyncio.run(orchestrator.execute(run_id))
