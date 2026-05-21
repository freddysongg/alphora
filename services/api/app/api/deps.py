from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from openai import AsyncOpenAI
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session, session_factory
from app.services.run_orchestrator import RunOrchestrator
from app.trading_agents.adapter import TradingAgentsAdapter
from app.workers.queue import get_run_queue


def get_run_orchestrator() -> RunOrchestrator:
    return RunOrchestrator(session_factory=session_factory, adapter=TradingAgentsAdapter())


@lru_cache(maxsize=1)
def _build_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("openai_api_key is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_openai_client() -> AsyncOpenAI:
    try:
        return _build_openai_client()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


SessionDep = Annotated[AsyncSession, Depends(get_session)]
OrchestratorDep = Annotated[RunOrchestrator, Depends(get_run_orchestrator)]
QueueDep = Annotated[Queue, Depends(get_run_queue)]
OpenAiClientDep = Annotated[AsyncOpenAI, Depends(get_openai_client)]
