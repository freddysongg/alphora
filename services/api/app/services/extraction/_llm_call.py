"""LlmClient integration for extraction.

This module is the first caller of ``app.services.llm.LlmClient``. The wrapper
takes injected ``llm_complete`` / ``orchestrator_pause`` / ``orchestrator_fail``
callables so test code can substitute fakes without touching network or DB
state. The production wiring is meant to pass:

* ``llm_complete`` -> an instance method bound to ``LlmClient.complete``
* ``orchestrator_pause`` -> ``RunOrchestrator.pause``
* ``orchestrator_fail`` -> ``RunOrchestrator.fail``

``LlmClient.complete`` currently commits the caller-provided session as part of
writing the call log (Phase 1 design). Callers must therefore treat the session
passed in here as "owned by the LLM call" -- do not interleave other writes on
the same session expecting them to roll back independently of the call log.
"""
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extraction._prompts import build_extraction_messages
from app.services.extraction.config import EXTRACTION_MODEL, PROMPT_VERSION
from app.services.llm import BudgetKilledError, BudgetPausedError, LlmCompletionResult


class ExtractionError(Exception):
    """Raised when an extraction call cannot return a usable result."""


async def call_llm_for_extraction(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    chunk_id: uuid.UUID,
    chunk_text: str,
    evidence_id: uuid.UUID,
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
) -> LlmCompletionResult:
    messages = build_extraction_messages(
        chunk_id=str(chunk_id),
        chunk_text=chunk_text,
    )

    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=EXTRACTION_MODEL,
            messages=messages,
            evidence_ids=[str(evidence_id)],
            prompt_version=PROMPT_VERSION,
            stage="extraction",
            agent_name="extraction",
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise ExtractionError("extraction paused by budget guard") from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise ExtractionError("extraction killed by budget guard") from exc

    return response


__all__ = ["ExtractionError", "call_llm_for_extraction"]
