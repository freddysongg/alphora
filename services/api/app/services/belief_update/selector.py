"""Hypothesis + chunk selection for the belief-update pass.

`select_belief_update_inputs` returns one `BeliefUpdateCandidate` per open
hypothesis that overlaps the run's touched entities. Each candidate carries
the chunks the LLM call will judge (after idempotency filtering and the
per-hypothesis cap).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import (
    Entity,
    EntityType,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_sector import SectorBrief as SectorBriefRow

_OPEN_HYPOTHESIS_STATUSES: frozenset[str] = frozenset({"proposed", "active"})
_BELIEF_RELATION_TYPES: frozenset[str] = frozenset(
    {
        RelationType.supports_hypothesis.value,
        RelationType.contradicts_hypothesis.value,
    }
)


@dataclass(frozen=True)
class BeliefUpdateCandidate:
    """One hypothesis paired with the chunks the LLM will judge for it."""

    hypothesis: Hypothesis
    chunks: list[EvidenceChunk]


@dataclass(frozen=True)
class _TouchedContext:
    """Entity IDs directly touched by a run's briefs, plus macro-brief flag."""

    sector_entity_ids: frozenset[uuid.UUID]
    company_entity_ids: frozenset[uuid.UUID]
    has_macro_brief: bool

    @property
    def all_direct_ids(self) -> frozenset[uuid.UUID]:
        return self.sector_entity_ids | self.company_entity_ids


async def select_belief_update_inputs(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    max_chunks_per_hypothesis: int,
) -> list[BeliefUpdateCandidate]:
    """Return open hypotheses + scope-relevant new chunks for this run.

    Walk: hypothesis.scope_entity_ids → run-scoped brief rows → evidence_ids →
    EvidenceChunks. Idempotency filter drops chunks where a belief relation on
    (hypothesis.entity_id, chunk_id) already exists. The N-cap takes the most
    recently created chunks first.
    """
    touched = await _load_touched_context(session=session, run_id=run_id)
    if not touched.all_direct_ids and not touched.has_macro_brief:
        return []

    hypotheses = await _load_open_hypotheses_in_scope(
        session=session, touched=touched
    )
    candidates: list[BeliefUpdateCandidate] = []
    for hypothesis in hypotheses:
        hypothesis_entity_id = hypothesis.entity_id
        if hypothesis_entity_id is None:
            continue
        evidence_ids = await _resolve_evidence_ids_for_scope(
            session=session,
            run_id=run_id,
            touched=touched,
            scope_entity_ids=[uuid.UUID(eid) for eid in hypothesis.scope_entity_ids],
        )
        if not evidence_ids:
            candidates.append(BeliefUpdateCandidate(hypothesis=hypothesis, chunks=[]))
            continue
        chunks = await _load_chunks_for_evidence(
            session=session, evidence_ids=evidence_ids
        )
        chunks = await _filter_chunks_with_existing_relation(
            session=session,
            hypothesis_entity_id=hypothesis_entity_id,
            chunks=chunks,
        )
        chunks = _cap_chunks(chunks, limit=max_chunks_per_hypothesis)
        candidates.append(BeliefUpdateCandidate(hypothesis=hypothesis, chunks=chunks))
    return candidates


async def _load_touched_context(
    *, session: AsyncSession, run_id: uuid.UUID
) -> _TouchedContext:
    sector_rows = (
        await session.execute(
            select(SectorBriefRow.sector_entity_id).where(
                SectorBriefRow.run_id == run_id
            )
        )
    ).scalars().all()

    company_rows = (
        await session.execute(
            select(CompanyThesisRow.company_entity_id).where(
                CompanyThesisRow.run_id == run_id
            )
        )
    ).scalars().all()

    macro_row = (
        await session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()

    return _TouchedContext(
        sector_entity_ids=frozenset(sector_rows),
        company_entity_ids=frozenset(company_rows),
        has_macro_brief=macro_row is not None,
    )


async def _load_open_hypotheses_in_scope(
    *, session: AsyncSession, touched: _TouchedContext
) -> list[Hypothesis]:
    rows = (
        await session.execute(
            select(Hypothesis).where(
                Hypothesis.status.in_(_OPEN_HYPOTHESIS_STATUSES),
                Hypothesis.archived_at.is_(None),
                Hypothesis.entity_id.is_not(None),
            )
        )
    ).scalars().all()

    direct_strs = {str(eid) for eid in touched.all_direct_ids}
    matching: list[Hypothesis] = []
    for row in rows:
        scope = row.scope_entity_ids
        if any(eid in direct_strs for eid in scope):
            matching.append(row)
        elif touched.has_macro_brief and scope:
            matching.append(row)
    return matching


async def _resolve_evidence_ids_for_scope(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    touched: _TouchedContext,
    scope_entity_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not scope_entity_ids:
        return set()

    entity_types = await _entity_types_for_ids(
        session=session, entity_ids=scope_entity_ids
    )
    evidence_ids: set[uuid.UUID] = set()
    has_macro_scope = False

    for entity_id in scope_entity_ids:
        kind = entity_types.get(entity_id)
        if kind == EntityType.sector.value:
            sector_rows = (
                await session.execute(
                    select(SectorBriefRow).where(
                        SectorBriefRow.run_id == run_id,
                        SectorBriefRow.sector_entity_id == entity_id,
                    )
                )
            ).scalars().all()
            for sector_row in sector_rows:
                evidence_ids.update(_extract_evidence_ids_from_payload(sector_row.payload))
        elif kind == EntityType.company.value:
            company_rows = (
                await session.execute(
                    select(CompanyThesisRow).where(
                        CompanyThesisRow.run_id == run_id,
                        CompanyThesisRow.company_entity_id == entity_id,
                    )
                )
            ).scalars().all()
            for company_row in company_rows:
                evidence_ids.update(_extract_evidence_ids_from_payload(company_row.payload))
        else:
            has_macro_scope = True

    if has_macro_scope and touched.has_macro_brief:
        macro_row = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalar_one_or_none()
        if macro_row is not None:
            for raw in macro_row.evidence_ids or []:
                evidence_ids.add(uuid.UUID(raw))

    return evidence_ids


async def _entity_types_for_ids(
    *, session: AsyncSession, entity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    rows = (
        await session.execute(
            select(Entity.id, Entity.type).where(Entity.id.in_(entity_ids))
        )
    ).all()
    return {row.id: row.type for row in rows}


def _extract_evidence_ids_from_payload(payload: object) -> set[uuid.UUID]:
    if not isinstance(payload, dict):
        return set()
    raw = payload.get("evidence_ids", [])
    if not isinstance(raw, list):
        return set()
    out: set[uuid.UUID] = set()
    for item in raw:
        try:
            out.add(uuid.UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


async def _load_chunks_for_evidence(
    *, session: AsyncSession, evidence_ids: set[uuid.UUID]
) -> list[EvidenceChunk]:
    if not evidence_ids:
        return []
    rows = (
        await session.execute(
            select(EvidenceChunk)
            .where(EvidenceChunk.evidence_id.in_(evidence_ids))
            .order_by(EvidenceChunk.created_at.desc(), EvidenceChunk.id.asc())
        )
    ).scalars().all()
    return list(rows)


async def _filter_chunks_with_existing_relation(
    *,
    session: AsyncSession,
    hypothesis_entity_id: uuid.UUID,
    chunks: list[EvidenceChunk],
) -> list[EvidenceChunk]:
    if not chunks:
        return []
    candidate_ids = [chunk.id for chunk in chunks]
    existing = (
        await session.execute(
            select(Relation.chunk_id).where(
                Relation.to_id == hypothesis_entity_id,
                Relation.chunk_id.in_(candidate_ids),
                Relation.type.in_(_BELIEF_RELATION_TYPES),
            )
        )
    ).scalars().all()
    blocked = {chunk_id for chunk_id in existing if chunk_id is not None}
    return [chunk for chunk in chunks if chunk.id not in blocked]


def _cap_chunks(
    chunks: list[EvidenceChunk], *, limit: int
) -> list[EvidenceChunk]:
    if limit <= 0:
        return []
    if len(chunks) <= limit:
        return chunks
    return chunks[:limit]


__all__ = [
    "BeliefUpdateCandidate",
    "select_belief_update_inputs",
]
