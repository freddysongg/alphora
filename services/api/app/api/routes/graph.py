import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_graph import DataSource, Evidence, EvidenceChunk
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
