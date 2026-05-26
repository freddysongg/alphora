from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from openai import AsyncOpenAI
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session, session_factory
from app.services.run_orchestrator import RunOrchestrator
from app.workers.queue import get_run_queue


def get_run_orchestrator() -> RunOrchestrator:
    return RunOrchestrator(session_factory=session_factory)


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


async def verify_human_token(
    x_human_token: str | None = Header(default=None, alias="X-Human-Token"),
) -> str:
    """Reject if env-var is empty (503), header missing/mismatched (401).

    Returns the single-user v1 identity string `"human:default"` on match.
    Phase 7 has no multi-user OAuth/JWT — spec §13 resolution #7.
    """
    settings = get_settings()
    stored = settings.human_approval_token.get_secret_value()
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HUMAN_APPROVAL_TOKEN not configured",
        )
    if x_human_token is None or x_human_token != stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing human approval token",
        )
    return "human:default"


HumanTokenDep = Annotated[str, Depends(verify_human_token)]
