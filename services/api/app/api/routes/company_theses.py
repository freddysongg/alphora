import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_runs import ResearchRun
from app.schemas.company_thesis import CompanyThesis, CompanyThesisPublic
from app.schemas.macro_brief import ChunkLookup
from app.schemas.sector_brief import JudgePublic, JudgeStatus

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
    "/{run_id}/companies/{company_entity_id}",
    response_model=CompanyThesisPublic,
)
async def get_company_thesis(
    run_id: uuid.UUID,
    company_entity_id: uuid.UUID,
    session: SessionDep,
) -> CompanyThesisPublic:
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
            detail="company thesis not available for this strategy",
        )
    row = (
        await session.execute(
            select(CompanyThesisRow)
            .where(CompanyThesisRow.run_id == run_id)
            .where(CompanyThesisRow.company_entity_id == company_entity_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="company thesis not yet available",
        )

    thesis = CompanyThesis.model_validate(row.payload)
    judge = JudgePublic(
        status=JudgeStatus(row.judge_status),
        reasons=list(row.judge_reasons or []),
        call_id=row.judge_call_id,
    )
    chunk_ids = [claim.chunk_id for claim in thesis.cited_claims]
    chunks = await _load_chunks(session=session, chunk_ids=chunk_ids)
    return CompanyThesisPublic(thesis=thesis, judge=judge, chunks=chunks)


__all__ = ["router"]
