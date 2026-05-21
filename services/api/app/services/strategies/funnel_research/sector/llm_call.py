"""Sector synthesis LLM call wrapper.

Mirrors `_llm_call.call_synthesis` but for the per-sector `SectorBrief`
output. Budget pause/kill is routed through the injected orchestrator.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, SectorCall
from app.schemas.sector_brief import SectorBrief
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)
from app.services.strategies.funnel_research._errors import (
    FunnelResearchBudgetHaltError,
    FunnelResearchError,
)
from app.services.strategies.funnel_research.config import PROMPT_VERSION, SYNTHESIS_MODEL
from app.services.strategies.funnel_research.sector.prompts import (
    build_sector_messages,
)


async def call_sector_synthesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    macro_brief: MacroBrief,
    sector_call: SectorCall,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    evidence_ids: list[uuid.UUID],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    regeneration_feedback: list[str] | None,
) -> SectorBrief:
    messages = build_sector_messages(
        macro_brief=macro_brief,
        sector_call=sector_call,
        digest_markdown=digest_markdown,
        chunks=chunks,
        evidence_ids=evidence_ids,
        regeneration_feedback=regeneration_feedback,
    )
    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=SYNTHESIS_MODEL,
            messages=messages,
            evidence_ids=[str(eid) for eid in evidence_ids],
            prompt_version=PROMPT_VERSION,
            stage="sector_synthesis",
            agent_name="synthesis",
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise FunnelResearchBudgetHaltError(
            f"sector synthesis paused by budget guard: {sector_call.sector_name}"
        ) from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise FunnelResearchBudgetHaltError(
            f"sector synthesis killed by budget guard: {sector_call.sector_name}"
        ) from exc

    try:
        raw: Any = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise FunnelResearchError(
            f"sector synthesis returned non-JSON output for "
            f"{sector_call.sector_name}: {exc}"
        ) from exc

    try:
        return SectorBrief.model_validate(raw)
    except ValidationError as exc:
        raise FunnelResearchError(
            f"sector synthesis output failed schema validation for "
            f"{sector_call.sector_name}: {exc}"
        ) from exc


__all__ = ["call_sector_synthesis"]
