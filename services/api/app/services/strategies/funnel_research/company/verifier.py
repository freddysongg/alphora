"""Deterministic verifier for `CompanyThesis` outputs.

Checks:
- Every `cited_claim.exact_quote` appears verbatim (whitespace-normalized) in
  one of the source chunks.
- The thesis's `company_name` matches the requested company.
- The thesis's `company_entity_id` matches the resolved company entity id.
- The thesis's `sector_entity_id` matches the parent sector entity id.

Runs a bounded regen loop matching the sector verifier's behavior. After the
final attempt, persists the thesis with `verifier_status='quote_unverified'`
when reasons remain.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.company_thesis import CompanyThesis
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import VerifierStatus
from app.services.run_events import emit_run_event
from app.services.strategies.funnel_research.company.selector import CompanyIdea
from app.services.strategies.funnel_research.config import MAX_REGENERATIONS

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class CompanyVerificationResult:
    is_valid: bool
    reasons: list[str]


@dataclass(frozen=True)
class CompanyRegenLoopResult:
    thesis: CompanyThesis
    regeneration_count: int
    reasons: list[str]


def verify_company_once(
    *,
    thesis: CompanyThesis,
    chunks: list[EvidenceChunkRef],
    company_idea: CompanyIdea,
    company_entity_id: uuid.UUID,
) -> CompanyVerificationResult:
    chunk_lookup: dict[uuid.UUID, EvidenceChunkRef] = {c.chunk_id: c for c in chunks}
    reasons: list[str] = []

    if thesis.company_name != company_idea.company_name:
        reasons.append(
            f"company_name mismatch: got {thesis.company_name!r}, "
            f"expected {company_idea.company_name!r}"
        )
    if thesis.company_entity_id != company_entity_id:
        reasons.append(
            f"company_entity_id mismatch: got {thesis.company_entity_id}, "
            f"expected {company_entity_id}"
        )
    if thesis.sector_entity_id != company_idea.sector_entity_id:
        reasons.append(
            f"sector_entity_id mismatch: got {thesis.sector_entity_id}, "
            f"expected {company_idea.sector_entity_id}"
        )

    for claim in thesis.cited_claims:
        chunk = chunk_lookup.get(claim.chunk_id)
        if chunk is None:
            reasons.append(f"chunk_id not in corpus: {claim.chunk_id}")
            continue
        if _normalize_whitespace(claim.exact_quote) not in _normalize_whitespace(
            chunk.text
        ):
            reasons.append(
                f"quote not in chunk: {claim.exact_quote!r} "
                f"(chunk_id={chunk.chunk_id})"
            )

    return CompanyVerificationResult(is_valid=not reasons, reasons=reasons)


async def run_company_regen_loop(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    initial_thesis: CompanyThesis,
    chunks: list[EvidenceChunkRef],
    company_idea: CompanyIdea,
    company_entity_id: uuid.UUID,
    regenerate: Callable[[list[str]], Awaitable[CompanyThesis]],
) -> CompanyRegenLoopResult:
    current = initial_thesis
    last_reasons: list[str] = []
    for attempt in range(MAX_REGENERATIONS + 1):
        result = verify_company_once(
            thesis=current,
            chunks=chunks,
            company_idea=company_idea,
            company_entity_id=company_entity_id,
        )
        if result.is_valid:
            verified = current.model_copy(
                update={
                    "verifier_status": VerifierStatus.verified,
                    "regeneration_count": attempt,
                }
            )
            return CompanyRegenLoopResult(
                thesis=verified, regeneration_count=attempt, reasons=[]
            )
        last_reasons = result.reasons
        if attempt == MAX_REGENERATIONS:
            break
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=(
                f"company {company_idea.company_name!r} verifier regeneration "
                f"{attempt + 1}/{MAX_REGENERATIONS}: "
                f"{len(result.reasons)} rejections"
            ),
            data={
                "event": "company_verifier_regeneration",
                "company": company_idea.company_name,
                "attempt": attempt + 1,
                "reasons": result.reasons,
            },
        )
        current = await regenerate(result.reasons)

    failed = current.model_copy(
        update={
            "verifier_status": VerifierStatus.quote_unverified,
            "regeneration_count": MAX_REGENERATIONS,
        }
    )
    return CompanyRegenLoopResult(
        thesis=failed, regeneration_count=MAX_REGENERATIONS, reasons=last_reasons
    )


__all__ = [
    "CompanyRegenLoopResult",
    "CompanyVerificationResult",
    "run_company_regen_loop",
    "verify_company_once",
]
