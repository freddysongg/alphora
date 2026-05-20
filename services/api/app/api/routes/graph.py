import uuid
from collections import Counter
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import DataSource, Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.graph import (
    DataSourcePublic,
    EvidenceChunkPublic,
    EvidencePublic,
    EvidenceTracePublic,
)

router = APIRouter()

_CONTEXT_RADIUS_MIN = 0
_CONTEXT_RADIUS_MAX = 10
_CONTEXT_RADIUS_DEFAULT = 2


@router.get("/evidence/by-evidence/{evidence_id}", response_model=EvidenceTracePublic)
async def get_evidence_trace_by_evidence(
    evidence_id: uuid.UUID,
    session: SessionDep,
    context_radius: Annotated[
        int,
        Query(ge=_CONTEXT_RADIUS_MIN, le=_CONTEXT_RADIUS_MAX),
    ] = _CONTEXT_RADIUS_DEFAULT,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
) -> EvidenceTracePublic:
    """Trace endpoint addressable by Evidence.id.

    Brief schemas store `Evidence.id` values in their `evidence_ids` arrays
    (themes, sector calls, watch items, hypotheses). Those ids are not chunk
    ids, so the chunk-id endpoint cannot resolve them. This endpoint resolves
    them to the chunk most frequently referenced in cited_claims across all
    macro / sector / company briefs, falling back to the lowest `chunk_index`
    when no citation references any chunk of the evidence.

    When `run_id` is provided, citation counts are restricted to that run.
    """
    chunks = (
        (
            await session.execute(
                select(EvidenceChunk)
                .where(EvidenceChunk.evidence_id == evidence_id)
                .order_by(EvidenceChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evidence not found",
        )
    selected = await _pick_most_cited_chunk(
        session=session, chunks=chunks, run_id=run_id
    )
    return await _build_trace_for_chunk(
        session=session, selected=selected, context_radius=context_radius
    )


async def _pick_most_cited_chunk(
    *,
    session: SessionDep,
    chunks: Sequence[EvidenceChunk],
    run_id: uuid.UUID | None = None,
) -> EvidenceChunk:
    chunk_id_to_chunk = {chunk.id: chunk for chunk in chunks}
    citation_counts: Counter[uuid.UUID] = Counter()

    macro_query = select(MacroBriefRow.cited_claims)
    sector_query = select(SectorBriefRow.payload)
    company_query = select(CompanyThesisRow.payload)
    if run_id is not None:
        macro_query = macro_query.where(MacroBriefRow.run_id == run_id)
        sector_query = sector_query.where(SectorBriefRow.run_id == run_id)
        company_query = company_query.where(CompanyThesisRow.run_id == run_id)

    macro_cited = (await session.execute(macro_query)).scalars().all()
    for claims in macro_cited:
        _accumulate_chunk_citations(claims, chunk_id_to_chunk, citation_counts)

    sector_payloads = (await session.execute(sector_query)).scalars().all()
    for payload in sector_payloads:
        _accumulate_chunk_citations(
            _extract_cited_claims(payload), chunk_id_to_chunk, citation_counts
        )

    company_payloads = (await session.execute(company_query)).scalars().all()
    for payload in company_payloads:
        _accumulate_chunk_citations(
            _extract_cited_claims(payload), chunk_id_to_chunk, citation_counts
        )

    if not citation_counts:
        return chunks[0]

    best_chunk_id, _ = max(
        citation_counts.items(),
        key=lambda entry: (entry[1], -chunk_id_to_chunk[entry[0]].chunk_index),
    )
    return chunk_id_to_chunk[best_chunk_id]


def _extract_cited_claims(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        return []
    claims = payload.get("cited_claims")
    if not isinstance(claims, list):
        return []
    return claims


def _accumulate_chunk_citations(
    claims: object,
    chunk_id_to_chunk: dict[uuid.UUID, EvidenceChunk],
    counts: Counter[uuid.UUID],
) -> None:
    if not isinstance(claims, list):
        return
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        raw_chunk_id = claim.get("chunk_id")
        if not isinstance(raw_chunk_id, str):
            continue
        try:
            chunk_id = uuid.UUID(raw_chunk_id)
        except ValueError:
            continue
        if chunk_id in chunk_id_to_chunk:
            counts[chunk_id] += 1


@router.get("/evidence/{chunk_id}", response_model=EvidenceTracePublic)
async def get_evidence_trace(
    chunk_id: uuid.UUID,
    session: SessionDep,
    context_radius: Annotated[
        int,
        Query(ge=_CONTEXT_RADIUS_MIN, le=_CONTEXT_RADIUS_MAX),
    ] = _CONTEXT_RADIUS_DEFAULT,
) -> EvidenceTracePublic:
    selected = (
        await session.execute(
            select(EvidenceChunk).where(EvidenceChunk.id == chunk_id)
        )
    ).scalar_one_or_none()
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evidence chunk not found",
        )
    return await _build_trace_for_chunk(
        session=session, selected=selected, context_radius=context_radius
    )


async def _build_trace_for_chunk(
    *,
    session: SessionDep,
    selected: EvidenceChunk,
    context_radius: int,
) -> EvidenceTracePublic:
    evidence = (
        await session.execute(
            select(Evidence).where(Evidence.id == selected.evidence_id)
        )
    ).scalar_one()

    data_source: DataSource | None = None
    if evidence.source_id is not None:
        data_source = (
            await session.execute(
                select(DataSource).where(DataSource.id == evidence.source_id)
            )
        ).scalar_one_or_none()

    low = selected.chunk_index - context_radius
    high = selected.chunk_index + context_radius
    context_rows = (
        (
            await session.execute(
                select(EvidenceChunk)
                .where(EvidenceChunk.evidence_id == evidence.id)
                .where(EvidenceChunk.chunk_index >= low)
                .where(EvidenceChunk.chunk_index <= high)
                .order_by(EvidenceChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )

    return EvidenceTracePublic(
        chunk=EvidenceChunkPublic.model_validate(selected),
        evidence=EvidencePublic.model_validate(evidence),
        data_source=(
            DataSourcePublic.model_validate(data_source)
            if data_source is not None
            else None
        ),
        context_chunks=[EvidenceChunkPublic.model_validate(row) for row in context_rows],
    )


__all__ = ["router"]
