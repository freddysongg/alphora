from typing import Annotated

from fastapi import Depends
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session, session_factory
from app.services.run_orchestrator import RunOrchestrator
from app.trading_agents.adapter import TradingAgentsAdapter
from app.workers.queue import get_run_queue


def get_run_orchestrator() -> RunOrchestrator:
    return RunOrchestrator(session_factory=session_factory, adapter=TradingAgentsAdapter())


SessionDep = Annotated[AsyncSession, Depends(get_session)]
OrchestratorDep = Annotated[RunOrchestrator, Depends(get_run_orchestrator)]
QueueDep = Annotated[Queue, Depends(get_run_queue)]
