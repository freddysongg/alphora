import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_runs import ResearchRun
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.macro_brief import ChunkLookup
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
)

router = APIRouter()


async def _load_chunks(
    *,
    session: AsyncSession,
    chunk_ids: list[uuid.UUID],
) -> list[ChunkLookup]:
    if not chunk_ids:
        return []
    chunk_rows = (
        await session.execute(
            select(EvidenceChunk, Evidence.source)
            .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
            .where(EvidenceChunk.id.in_(chunk_ids))
        )
    ).all()
    return [
        ChunkLookup(
            chunk_id=chunk_row.id,
            evidence_id=chunk_row.evidence_id,
            source=source,
            text=chunk_row.text,
            attributes=chunk_row.attributes or {},
        )
        for chunk_row, source in chunk_rows
    ]


@router.get(
    "/{run_id}/sectors/{sector_entity_id}",
    response_model=SectorBriefPublic,
)
async def get_sector_brief(
    run_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    session: SessionDep,
) -> SectorBriefPublic:
    run = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="research run not found"
        )
    if run.strategy != "funnel_research":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sector brief not available for this strategy",
        )
    row = (
        await session.execute(
            select(SectorBriefRow)
            .where(SectorBriefRow.run_id == run_id)
            .where(SectorBriefRow.sector_entity_id == sector_entity_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sector brief not yet available",
        )

    brief = SectorBrief.model_validate(row.payload)
    judge = JudgePublic(
        status=JudgeStatus(row.judge_status),
        reasons=list(row.judge_reasons or []),
        call_id=row.judge_call_id,
    )
    chunks = await _load_chunks(
        session=session,
        chunk_ids=[claim.chunk_id for claim in brief.cited_claims],
    )
    return SectorBriefPublic(brief=brief, judge=judge, chunks=chunks)


__all__ = ["router"]
