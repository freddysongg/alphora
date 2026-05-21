"""Persist sector candidates into the entity graph.

For each `ExtractionResult`:
- Resolve every `CandidateEntity` via the existing `resolve_candidate` pipeline.
- Persist a `Relation` only when BOTH endpoints (subj_span, obj_span) resolve
  to concrete entity ids — relations with an unresolved endpoint are skipped
  and recorded as warn events.

Returns the mapping `text_span -> entity_id` so downstream synthesis can
link cited claims back to canonical entities, plus counts.

Phase 3 — every persisted `Relation` carries its full provenance:
`chunk_id`, resolved `source_id` (chunk → evidence), top-level `quote`,
`is_explicit`, `sign` (-1 for contradicts_hypothesis, +1 otherwise),
`relevance` (1.0 when explicit, 0.6 when inferred), `extracted_by_model`
and `prompt_version`. After the batch lands, belief is recomputed for
every hypothesis affected by a supports/contradicts relation in the batch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk, Relation, RelationType
from app.db.models_runs import RunEventLevel
from app.schemas.common import RelationTypeEnum
from app.schemas.extraction import (
    CandidateEntity,
    CandidateRelation,
    ExtractionResult,
)
from app.services.belief import recompute_beliefs_for_relations
from app.services.entity_resolution import (
    LlmDisambiguator,
    resolve_candidate,
)
from app.services.entity_resolution._types import CandidateLike
from app.services.run_events import emit_run_event


@dataclass(frozen=True)
class SectorGraphPersistOutcome:
    entity_id_by_span: dict[str, uuid.UUID] = field(default_factory=dict)
    resolved_entity_count: int = 0
    persisted_relation_count: int = 0
    skipped_relation_count: int = 0
    recomputed_hypothesis_ids: list[uuid.UUID] = field(default_factory=list)


async def persist_sector_candidates(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    extraction_results: list[ExtractionResult],
    llm_disambiguator: LlmDisambiguator | None = None,
) -> SectorGraphPersistOutcome:
    entity_id_by_span: dict[str, uuid.UUID] = {}
    resolved_count = 0
    persisted_relations = 0
    skipped_relations = 0
    persisted_relation_ids: list[uuid.UUID] = []

    for result in extraction_results:
        for candidate in result.candidate_entities:
            entity_id = await _resolve_entity(
                session=session,
                candidate=candidate,
                llm_disambiguator=llm_disambiguator,
            )
            if entity_id is not None:
                entity_id_by_span[candidate.text_span] = entity_id
                resolved_count += 1

    chunk_ids = {
        relation.chunk_id
        for result in extraction_results
        for relation in result.candidate_relations
    }
    chunk_to_evidence = await _resolve_chunk_to_evidence(
        session=session, chunk_ids=chunk_ids
    )

    for result in extraction_results:
        for relation in result.candidate_relations:
            relation_id = await _persist_relation(
                session=session,
                run_id=run_id,
                relation=relation,
                entity_id_by_span=entity_id_by_span,
                prompt_version=result.prompt_version,
                extracted_by_model=result.model_id,
                evidence_id=chunk_to_evidence.get(relation.chunk_id),
            )
            if relation_id is not None:
                persisted_relations += 1
                persisted_relation_ids.append(relation_id)
            else:
                skipped_relations += 1

    if persisted_relation_ids:
        await session.flush()
    recomputed = await recompute_beliefs_for_relations(
        session=session, relation_ids=persisted_relation_ids
    )
    await session.commit()

    return SectorGraphPersistOutcome(
        entity_id_by_span=entity_id_by_span,
        resolved_entity_count=resolved_count,
        persisted_relation_count=persisted_relations,
        skipped_relation_count=skipped_relations,
        recomputed_hypothesis_ids=sorted(recomputed.keys(), key=str),
    )


async def _resolve_entity(
    *,
    session: AsyncSession,
    candidate: CandidateEntity,
    llm_disambiguator: LlmDisambiguator | None,
) -> uuid.UUID | None:
    outcome = await resolve_candidate(
        session=session,
        candidate=cast(CandidateLike, candidate),
        llm_disambiguator=llm_disambiguator,
    )
    return outcome.chosen_entity_id


async def _persist_relation(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    relation: CandidateRelation,
    entity_id_by_span: dict[str, uuid.UUID],
    prompt_version: str,
    extracted_by_model: str,
    evidence_id: uuid.UUID | None,
) -> uuid.UUID | None:
    from_id = entity_id_by_span.get(relation.subj_span)
    to_id = entity_id_by_span.get(relation.obj_span)
    if from_id is None or to_id is None:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=(
                f"sector relation skipped: subj={relation.subj_span!r} "
                f"obj={relation.obj_span!r} (unresolved endpoint)"
            ),
            data={
                "event": "sector_relation_skipped",
                "subj_span": relation.subj_span,
                "obj_span": relation.obj_span,
                "predicate": relation.predicate.value
                if isinstance(relation.predicate, RelationTypeEnum)
                else str(relation.predicate),
                "reason": "unresolved_endpoint",
            },
        )
        return None
    if from_id == to_id:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=(
                f"sector relation skipped: self-loop on {relation.subj_span!r}"
            ),
            data={
                "event": "sector_relation_skipped",
                "subj_span": relation.subj_span,
                "obj_span": relation.obj_span,
                "predicate": relation.predicate.value
                if isinstance(relation.predicate, RelationTypeEnum)
                else str(relation.predicate),
                "reason": "self_loop",
            },
        )
        return None
    predicate_value = (
        relation.predicate.value
        if isinstance(relation.predicate, RelationTypeEnum)
        else str(relation.predicate)
    )
    sign = (
        -1.0
        if predicate_value == RelationType.contradicts_hypothesis.value
        else 1.0
    )
    relevance = 1.0 if relation.is_explicit else 0.6
    chunk_id = relation.chunk_id if evidence_id is not None else None
    row = Relation(
        from_id=from_id,
        to_id=to_id,
        type=predicate_value,
        attributes={
            "extraction_confidence": relation.extraction_confidence,
            "is_explicit": relation.is_explicit,
            "exact_quote": relation.exact_quote,
        },
        extraction_confidence=relation.extraction_confidence,
        source_id=evidence_id,
        chunk_id=chunk_id,
        quote=relation.exact_quote,
        relevance=relevance,
        extracted_by_model=extracted_by_model,
        prompt_version=prompt_version,
        is_explicit=relation.is_explicit,
        sign=sign,
    )
    session.add(row)
    await session.flush()
    return row.id


async def _resolve_chunk_to_evidence(
    *,
    session: AsyncSession,
    chunk_ids: set[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID]:
    """Single round-trip lookup from chunk id → evidence id."""
    if not chunk_ids:
        return {}
    rows = (
        await session.execute(
            select(EvidenceChunk.id, EvidenceChunk.evidence_id).where(
                EvidenceChunk.id.in_(chunk_ids)
            )
        )
    ).all()
    return {chunk_id: evidence_id for chunk_id, evidence_id in rows}


__all__ = [
    "SectorGraphPersistOutcome",
    "persist_sector_candidates",
]
