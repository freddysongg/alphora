import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, MacroBriefScope
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research._prompts import build_synthesis_messages
from app.services.strategies.funnel_research.config import SYNTHESIS_MODEL


async def call_synthesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    scope: MacroBriefScope,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    evidence_ids: list[uuid.UUID],
    regeneration_feedback: list[str] | None,
) -> MacroBrief:
    messages = build_synthesis_messages(
        scope=scope,
        digest_markdown=digest_markdown,
        chunks=chunks,
        allowed_sectors=frozenset(sector_entity_ids.keys()),
        sector_entity_ids=sector_entity_ids,
        regeneration_feedback=regeneration_feedback,
    )
    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=SYNTHESIS_MODEL,
            messages=messages,
            evidence_ids=[str(eid) for eid in evidence_ids],
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise FunnelResearchError("synthesis paused by budget guard") from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise FunnelResearchError("synthesis killed by budget guard") from exc

    try:
        raw: Any = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise FunnelResearchError(f"synthesis returned non-JSON output: {exc}") from exc

    try:
        return MacroBrief.model_validate(raw)
    except ValidationError as exc:
        raise FunnelResearchError(f"synthesis output failed schema validation: {exc}") from exc


__all__ = ["call_synthesis"]
