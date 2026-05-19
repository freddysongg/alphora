"""LLM judge for macro and sector briefs.

Runs only after the deterministic verifier passes. Asks the judge to scan
the brief for:
- Contradictions between cited claims and sector-call directions.
- Cited claims that the chunk text does not actually support.
- Sector-call directions that flip without supporting evidence.

The judge returns `{status: 'passed' | 'flagged', reasons: list[str]}`.
A flagged result counts against the existing regen cap.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.company_thesis import CompanyThesis
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief
from app.schemas.portfolio_brief import PortfolioBrief
from app.schemas.sector_brief import JudgePublic, JudgeStatus, SectorBrief
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
    LlmMessage,
)
from app.services.run_events import emit_run_event
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research.config import SYNTHESIS_MODEL

BriefKind = Literal["macro", "sector", "company", "portfolio"]


@dataclass(frozen=True)
class JudgeOutcome:
    public: JudgePublic
    regenerate_reasons: list[str]


_JUDGE_SYSTEM = (
    "You are a deterministic judge for research briefs. Read the brief and "
    "the source chunks. Output strictly JSON: "
    '{"status": "passed"|"flagged", "reasons": [string, ...]}. '
    "If passed, reasons may be empty. If flagged, list specific concrete reasons."
)


def _format_chunks(chunks: list[EvidenceChunkRef]) -> str:
    if not chunks:
        return "(no chunks)"
    blocks: list[str] = []
    for ref in sorted(chunks, key=lambda c: str(c.chunk_id)):
        source = str(ref.attributes.get("source", "unknown"))
        blocks.append(f"[chunk_id={ref.chunk_id}, source={source}]\n{ref.text}")
    return "\n\n".join(blocks)


def _build_messages(
    *,
    brief_kind: BriefKind,
    brief_json: str,
    chunks: list[EvidenceChunkRef],
) -> list[LlmMessage]:
    user_parts = [
        f"Brief kind: {brief_kind}",
        "",
        "Brief JSON:",
        brief_json,
        "",
        "Source chunks:",
        _format_chunks(chunks),
        "",
        'Output JSON only: {"status": "passed"|"flagged", "reasons": [string, ...]}',
    ]
    return [
        LlmMessage(role="system", content=_JUDGE_SYSTEM),
        LlmMessage(role="user", content="\n".join(user_parts)),
    ]


def _parse_judge_output(content: str) -> tuple[JudgeStatus, list[str]]:
    try:
        raw: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise FunnelResearchError(f"judge returned non-JSON output: {exc}") from exc
    if not isinstance(raw, dict):
        raise FunnelResearchError("judge output is not an object")
    status_value = raw.get("status")
    reasons_value = raw.get("reasons", [])
    if not isinstance(status_value, str):
        raise FunnelResearchError("judge output missing status string")
    try:
        status = JudgeStatus(status_value)
    except ValueError as exc:
        raise FunnelResearchError(
            f"judge output status must be passed|flagged, got {status_value!r}"
        ) from exc
    if status is JudgeStatus.not_run:
        raise FunnelResearchError("judge cannot return status=not_run")
    if not isinstance(reasons_value, list):
        raise FunnelResearchError("judge output reasons must be a list")
    reasons: list[str] = []
    for entry in reasons_value:
        if not isinstance(entry, str):
            raise FunnelResearchError("judge output reasons must be strings")
        reasons.append(entry)
    return status, reasons


async def run_judge(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief: MacroBrief | SectorBrief | CompanyThesis | PortfolioBrief,
    brief_kind: BriefKind,
    chunks: list[EvidenceChunkRef],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
) -> JudgeOutcome:
    """Run the LLM judge over a verified brief. Returns the judge outcome.

    On LLM/parse failure, emits a warn event and returns `status='not_run'`
    rather than failing the run. This makes the judge advisory: a missing
    verdict surfaces in the UI but does not block.

    Budget pause/kill is NOT advisory: it is routed through the orchestrator
    (pause/fail) and re-raised as `FunnelResearchError` so the caller's
    halt-on-paused logic engages.
    """
    brief_json = brief.model_dump_json()
    messages = _build_messages(
        brief_kind=brief_kind, brief_json=brief_json, chunks=chunks
    )
    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=SYNTHESIS_MODEL,
            messages=messages,
            evidence_ids=None,
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise FunnelResearchError(
            f"judge paused by budget guard: {brief_kind}"
        ) from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise FunnelResearchError(
            f"judge killed by budget guard: {brief_kind}"
        ) from exc
    except Exception as exc:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=f"judge call failed: {exc}",
            data={"event": "judge_failure", "reason": str(exc)},
        )
        return JudgeOutcome(
            public=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
            regenerate_reasons=[],
        )

    try:
        status, reasons = _parse_judge_output(response.content)
    except FunnelResearchError as exc:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=f"judge output unparseable: {exc}",
            data={"event": "judge_parse_failure", "reason": str(exc)},
        )
        return JudgeOutcome(
            public=JudgePublic(
                status=JudgeStatus.not_run, reasons=[], call_id=response.log_id
            ),
            regenerate_reasons=[],
        )

    public = JudgePublic(status=status, reasons=reasons, call_id=response.log_id)
    regen_reasons = reasons if status is JudgeStatus.flagged else []
    return JudgeOutcome(public=public, regenerate_reasons=regen_reasons)


__all__ = ["BriefKind", "JudgeOutcome", "run_judge"]
