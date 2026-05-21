"""Deterministic verifier for `SectorBrief` outputs.

Checks:
- Every `cited_claim.exact_quote` appears verbatim (whitespace-normalized) in
  one of the source chunks.
- The brief's `sector_name` matches the requested sector.
- The brief's `sector_entity_id` matches the requested sector's id.

Runs a bounded regen loop matching the macro verifier's behavior. After the
final attempt, persists the brief with `verifier_status='quote_unverified'`
when reasons remain.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import SectorCall, VerifierStatus
from app.schemas.sector_brief import SectorBrief
from app.services.run_events import emit_run_event
from app.services.strategies.funnel_research.config import MAX_REGENERATIONS

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class SectorVerificationResult:
    is_valid: bool
    reasons: list[str]


@dataclass(frozen=True)
class SectorRegenLoopResult:
    brief: SectorBrief
    regeneration_count: int
    reasons: list[str]


def verify_sector_once(
    *,
    brief: SectorBrief,
    chunks: list[EvidenceChunkRef],
    sector_call: SectorCall,
) -> SectorVerificationResult:
    chunk_lookup: dict[uuid.UUID, EvidenceChunkRef] = {c.chunk_id: c for c in chunks}
    reasons: list[str] = []

    if brief.sector_name != sector_call.sector_name:
        reasons.append(
            f"sector_name mismatch: got {brief.sector_name!r}, "
            f"expected {sector_call.sector_name!r}"
        )
    if brief.sector_entity_id != sector_call.sector_entity_id:
        reasons.append(
            f"sector_entity_id mismatch: got {brief.sector_entity_id}, "
            f"expected {sector_call.sector_entity_id}"
        )

    for claim in brief.cited_claims:
        chunk = chunk_lookup.get(claim.chunk_id)
        if chunk is None:
            reasons.append(f"chunk_id not in corpus: {claim.chunk_id}")
            continue
        if _normalize_whitespace(claim.exact_quote) not in _normalize_whitespace(chunk.text):
            reasons.append(
                f"quote not in chunk: {claim.exact_quote!r} "
                f"(chunk_id={chunk.chunk_id})"
            )

    return SectorVerificationResult(is_valid=not reasons, reasons=reasons)


async def run_sector_regen_loop(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    initial_brief: SectorBrief,
    chunks: list[EvidenceChunkRef],
    sector_call: SectorCall,
    regenerate: Callable[[list[str]], Awaitable[SectorBrief]],
) -> SectorRegenLoopResult:
    current = initial_brief
    last_reasons: list[str] = []
    for attempt in range(MAX_REGENERATIONS + 1):
        result = verify_sector_once(
            brief=current, chunks=chunks, sector_call=sector_call
        )
        if result.is_valid:
            verified = current.model_copy(
                update={
                    "verifier_status": VerifierStatus.verified,
                    "regeneration_count": attempt,
                }
            )
            return SectorRegenLoopResult(
                brief=verified, regeneration_count=attempt, reasons=[]
            )
        last_reasons = result.reasons
        if attempt == MAX_REGENERATIONS:
            break
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=(
                f"sector {sector_call.sector_name!r} verifier regeneration "
                f"{attempt + 1}/{MAX_REGENERATIONS}: "
                f"{len(result.reasons)} rejections"
            ),
            data={
                "event": "sector_verifier_regeneration",
                "sector": sector_call.sector_name,
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
    return SectorRegenLoopResult(
        brief=failed, regeneration_count=MAX_REGENERATIONS, reasons=last_reasons
    )


__all__ = [
    "SectorRegenLoopResult",
    "SectorVerificationResult",
    "run_sector_regen_loop",
    "verify_sector_once",
]
