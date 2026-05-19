import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, VerifierStatus
from app.services.run_events import emit_run_event
from app.services.strategies.funnel_research.config import (
    ALLOWED_SECTOR_NAMES,
    MAX_REGENERATIONS,
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class VerificationResult:
    is_valid: bool
    reasons: list[str]


@dataclass(frozen=True)
class RegenLoopResult:
    brief: MacroBrief
    regeneration_count: int
    reasons: list[str]


def verify_once(
    *,
    brief: MacroBrief,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
) -> VerificationResult:
    chunk_lookup: dict[uuid.UUID, EvidenceChunkRef] = {c.chunk_id: c for c in chunks}
    reasons: list[str] = []

    for claim in brief.cited_claims:
        chunk = chunk_lookup.get(claim.chunk_id)
        if chunk is None:
            reasons.append(f"chunk_id not in corpus: {claim.chunk_id}")
            continue
        if _normalize_whitespace(claim.exact_quote) not in _normalize_whitespace(chunk.text):
            reasons.append(f"quote not in chunk: {claim.exact_quote!r} (chunk_id={chunk.chunk_id})")

    for call in brief.sector_calls:
        if call.sector_name not in ALLOWED_SECTOR_NAMES:
            reasons.append(f"sector name not in allowlist: {call.sector_name!r}")
            continue
        expected = sector_entity_ids.get(call.sector_name)
        if expected is None or expected != call.sector_entity_id:
            reasons.append(
                f"sector_entity_id mismatch: sector={call.sector_name!r} "
                f"got={call.sector_entity_id} expected={expected}"
            )

    return VerificationResult(is_valid=not reasons, reasons=reasons)


async def run_regen_loop(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    initial_brief: MacroBrief,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regenerate: Callable[[list[str]], Awaitable[MacroBrief]],
) -> RegenLoopResult:
    current = initial_brief
    last_reasons: list[str] = []
    for attempt in range(MAX_REGENERATIONS + 1):
        result = verify_once(brief=current, chunks=chunks, sector_entity_ids=sector_entity_ids)
        if result.is_valid:
            verified = current.model_copy(
                update={
                    "verifier_status": VerifierStatus.verified,
                    "regeneration_count": attempt,
                }
            )
            return RegenLoopResult(brief=verified, regeneration_count=attempt, reasons=[])
        last_reasons = result.reasons
        if attempt == MAX_REGENERATIONS:
            break
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=f"verifier regeneration {attempt + 1}/{MAX_REGENERATIONS}: {len(result.reasons)} rejections",
            data={"event": "verifier_regeneration", "attempt": attempt + 1, "reasons": result.reasons},
        )
        current = await regenerate(result.reasons)

    failed = current.model_copy(
        update={
            "verifier_status": VerifierStatus.quote_unverified,
            "regeneration_count": MAX_REGENERATIONS,
        }
    )
    return RegenLoopResult(brief=failed, regeneration_count=MAX_REGENERATIONS, reasons=last_reasons)


__all__ = ["RegenLoopResult", "VerificationResult", "run_regen_loop", "verify_once"]
