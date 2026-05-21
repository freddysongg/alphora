"""Company synthesis LLM call wrapper.

Mirrors `sector.llm_call.call_sector_synthesis` but for the per-company
`CompanyThesis` output. Budget pause/kill is routed through the injected
orchestrator.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.company_thesis import CompanyThesis
from app.schemas.extraction import EvidenceChunkRef
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
from app.services.strategies.funnel_research.company.prompts import (
    build_company_messages,
)
from app.services.strategies.funnel_research.company.selector import CompanyIdea
from app.services.strategies.funnel_research.config import PROMPT_VERSION, SYNTHESIS_MODEL


async def call_company_synthesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_idea: CompanyIdea,
    company_entity_id: uuid.UUID,
    sector_brief: SectorBrief,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    evidence_ids: list[uuid.UUID],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    regeneration_feedback: list[str] | None,
) -> CompanyThesis:
    messages = build_company_messages(
        company_idea=company_idea,
        company_entity_id=company_entity_id,
        sector_brief=sector_brief,
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
            stage="company_synthesis",
            agent_name="synthesis",
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise FunnelResearchBudgetHaltError(
            f"company synthesis paused by budget guard: {company_idea.company_name}"
        ) from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise FunnelResearchBudgetHaltError(
            f"company synthesis killed by budget guard: {company_idea.company_name}"
        ) from exc

    try:
        raw: Any = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise FunnelResearchError(
            f"company synthesis returned non-JSON output for "
            f"{company_idea.company_name}: {exc}"
        ) from exc

    try:
        return CompanyThesis.model_validate(raw)
    except ValidationError as exc:
        raise FunnelResearchError(
            f"company synthesis output failed schema validation for "
            f"{company_idea.company_name}: {exc}"
        ) from exc


__all__ = ["call_company_synthesis"]
