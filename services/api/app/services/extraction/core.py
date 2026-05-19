import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError
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

    raw_entities = _require_candidate_list(payload, key="candidate_entities")
    raw_relations = _require_candidate_list(payload, key="candidate_relations")

    candidate_entities = _validate_candidates(
        raw_entities,
        model=CandidateEntity,
        chunk_id=chunk.chunk_id,
        key="candidate_entities",
    )
    candidate_relations = _validate_candidates(
        raw_relations,
        model=CandidateRelation,
        chunk_id=chunk.chunk_id,
        key="candidate_relations",
    )

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


def _require_candidate_list(payload: dict[str, Any], *, key: str) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ExtractionError(
            f"LLM JSON payload {key!r} must be a list, got {type(value).__name__}"
        )
    return value


def _validate_candidates[T: BaseModel](
    rows: list[Any],
    *,
    model: type[T],
    chunk_id: uuid.UUID,
    key: str,
) -> list[T]:
    candidates: list[T] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ExtractionError(
                f"LLM JSON payload {key!r}[{index}] must be an object, "
                f"got {type(row).__name__}"
            )
        try:
            candidates.append(model.model_validate({**row, "chunk_id": chunk_id}))
        except ValidationError as exc:
            raise ExtractionError(
                f"LLM JSON payload {key!r}[{index}] failed validation: {exc}"
            ) from exc
    return candidates


__all__ = ["extract_from_chunk"]
