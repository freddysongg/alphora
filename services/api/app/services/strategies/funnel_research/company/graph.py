"""Persist company candidates into the entity graph.

For each `ExtractionResult`:
- Resolve every `CandidateEntity` via the existing `resolve_candidate` pipeline.
- Persist a `Relation` only when BOTH endpoints (subj_span, obj_span) resolve
  to concrete entity ids — relations with an unresolved endpoint are skipped
  and recorded as warn events.

Returns the mapping `text_span -> entity_id` so downstream synthesis can
link cited claims back to canonical entities, plus counts.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Relation
from app.db.models_runs import RunEventLevel
from app.schemas.common import RelationTypeEnum
from app.schemas.extraction import (
    CandidateEntity,
    CandidateRelation,
    ExtractionResult,
)
from app.services.entity_resolution import (
    LlmDisambiguator,
    resolve_candidate,
)
from app.services.entity_resolution._types import CandidateLike
from app.services.run_events import emit_run_event


@dataclass(frozen=True)
class CompanyGraphPersistOutcome:
    entity_id_by_span: dict[str, uuid.UUID] = field(default_factory=dict)
    resolved_entity_count: int = 0
    persisted_relation_count: int = 0
    skipped_relation_count: int = 0


async def persist_company_candidates(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    extraction_results: list[ExtractionResult],
    llm_disambiguator: LlmDisambiguator | None = None,
) -> CompanyGraphPersistOutcome:
    entity_id_by_span: dict[str, uuid.UUID] = {}
    resolved_count = 0
    persisted_relations = 0
    skipped_relations = 0

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

    for result in extraction_results:
        for relation in result.candidate_relations:
            persisted = await _persist_relation(
                session=session,
                run_id=run_id,
                relation=relation,
                entity_id_by_span=entity_id_by_span,
            )
            if persisted:
                persisted_relations += 1
            else:
                skipped_relations += 1

    await session.commit()

    return CompanyGraphPersistOutcome(
        entity_id_by_span=entity_id_by_span,
        resolved_entity_count=resolved_count,
        persisted_relation_count=persisted_relations,
        skipped_relation_count=skipped_relations,
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
) -> bool:
    from_id = entity_id_by_span.get(relation.subj_span)
    to_id = entity_id_by_span.get(relation.obj_span)
    if from_id is None or to_id is None:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=(
                f"company relation skipped: subj={relation.subj_span!r} "
                f"obj={relation.obj_span!r} (unresolved endpoint)"
            ),
            data={
                "event": "company_relation_skipped",
                "subj_span": relation.subj_span,
                "obj_span": relation.obj_span,
                "predicate": relation.predicate.value
                if isinstance(relation.predicate, RelationTypeEnum)
                else str(relation.predicate),
                "reason": "unresolved_endpoint",
            },
        )
        return False
    if from_id == to_id:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=(
                f"company relation skipped: self-loop on {relation.subj_span!r}"
            ),
            data={
                "event": "company_relation_skipped",
                "subj_span": relation.subj_span,
                "obj_span": relation.obj_span,
                "predicate": relation.predicate.value
                if isinstance(relation.predicate, RelationTypeEnum)
                else str(relation.predicate),
                "reason": "self_loop",
            },
        )
        return False
    predicate_value = (
        relation.predicate.value
        if isinstance(relation.predicate, RelationTypeEnum)
        else str(relation.predicate)
    )
    session.add(
        Relation(
            from_id=from_id,
            to_id=to_id,
            type=predicate_value,
            attributes={
                "extraction_confidence": relation.extraction_confidence,
                "is_explicit": relation.is_explicit,
                "exact_quote": relation.exact_quote,
            },
            extraction_confidence=relation.extraction_confidence,
        )
    )
    return True


__all__ = [
    "CompanyGraphPersistOutcome",
    "persist_company_candidates",
]
