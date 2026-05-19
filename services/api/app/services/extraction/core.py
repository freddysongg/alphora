import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import (
    CandidateEntity,
    CandidateRelation,
    EvidenceChunkRef,
    ExtractionResult,
)
from app.services.extraction._llm_call import ExtractionError, call_llm_for_extraction
from app.services.extraction._verifier import verify_candidates
from app.services.extraction.config import PROMPT_VERSION
from app.services.llm import LlmCompletionResult


async def extract_from_chunk(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    chunk: EvidenceChunkRef,
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
) -> ExtractionResult:
    response = await call_llm_for_extraction(
        session=session,
        run_id=run_id,
        chunk_id=chunk.chunk_id,
        chunk_text=chunk.text,
        evidence_id=chunk.evidence_id,
        llm_complete=llm_complete,
        orchestrator_pause=orchestrator_pause,
        orchestrator_fail=orchestrator_fail,
    )

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"LLM returned non-JSON content: {exc}") from exc

    if not isinstance(payload, dict):
        raise ExtractionError("LLM JSON payload was not an object")

    raw_entities = payload.get("candidate_entities", [])
    raw_relations = payload.get("candidate_relations", [])

    candidate_entities = [
        CandidateEntity.model_validate(_with_chunk_id(row, chunk.chunk_id))
        for row in raw_entities
    ]
    candidate_relations = [
        CandidateRelation.model_validate(_with_chunk_id(row, chunk.chunk_id))
        for row in raw_relations
    ]

    verifier_result = verify_candidates(
        chunk_text=chunk.text,
        candidate_entities=candidate_entities,
        candidate_relations=candidate_relations,
    )

    return ExtractionResult(
        chunk_id=chunk.chunk_id,
        candidate_entities=verifier_result.kept_entities,
        candidate_relations=verifier_result.kept_relations,
        model_id=response.model,
        prompt_version=PROMPT_VERSION,
        verified=len(verifier_result.rejection_reasons) == 0,
        rejection_reasons=verifier_result.rejection_reasons,
    )


def _with_chunk_id(row: dict[str, Any], chunk_id: uuid.UUID) -> dict[str, Any]:
    return {**row, "chunk_id": chunk_id}


__all__ = ["extract_from_chunk"]
