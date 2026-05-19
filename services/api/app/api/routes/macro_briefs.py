import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.macro_brief import (
    ChunkLookup,
    CitedClaim,
    MacroBrief,
    MacroBriefPublic,
    ProposedHypothesis,
    SectorCall,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
)

router = APIRouter()


def _hydrate_brief(row: MacroBriefRow) -> MacroBrief:
    return MacroBrief(
        themes=[Theme.model_validate(t) for t in row.themes],
        sector_calls=[SectorCall.model_validate(c) for c in row.sector_calls],
        watch_items=[WatchItem.model_validate(w) for w in row.watch_items],
        cited_claims=[CitedClaim.model_validate(c) for c in row.cited_claims],
        proposed_hypotheses=[
            ProposedHypothesis.model_validate(p) for p in row.proposed_hypotheses
        ],
        confidence=row.confidence,
        evidence_ids=[uuid.UUID(e) for e in row.evidence_ids],
        verifier_status=VerifierStatus(row.verifier_status),
        regeneration_count=row.regeneration_count,
    )


def _hydrate_judge(
    *,
    status_value: str,
    reasons: list[str] | None,
    call_id: uuid.UUID | None,
) -> JudgePublic:
    return JudgePublic(
        status=JudgeStatus(status_value),
        reasons=list(reasons or []),
        call_id=call_id,
    )


def _hydrate_sector_brief_row(row: SectorBriefRow) -> SectorBriefPublic:
    brief = SectorBrief.model_validate(row.payload)
    judge = _hydrate_judge(
        status_value=row.judge_status,
        reasons=row.judge_reasons,
        call_id=row.judge_call_id,
    )
    return SectorBriefPublic(brief=brief, judge=judge)


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


@router.get("/{run_id}/macro-brief", response_model=MacroBriefPublic)
async def get_macro_brief(run_id: uuid.UUID, session: SessionDep) -> MacroBriefPublic:
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
            detail="macro brief not available for this strategy",
        )
    row = (
        await session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="macro brief not yet available",
        )

    brief = _hydrate_brief(row)

    sector_rows = (
        (
            await session.execute(
                select(SectorBriefRow)
                .where(SectorBriefRow.run_id == run_id)
                .order_by(SectorBriefRow.created_at)
            )
        )
        .scalars()
        .all()
    )
    sector_briefs = [_hydrate_sector_brief_row(row) for row in sector_rows]

    chunk_id_set: set[uuid.UUID] = {claim.chunk_id for claim in brief.cited_claims}
    for sector_public in sector_briefs:
        chunk_id_set.update(
            claim.chunk_id for claim in sector_public.brief.cited_claims
        )
    chunks = await _load_chunks(session=session, chunk_ids=list(chunk_id_set))

    judge = _hydrate_judge(
        status_value=row.judge_status,
        reasons=row.judge_reasons,
        call_id=row.judge_call_id,
    )
    return MacroBriefPublic(
        brief=brief, judge=judge, chunks=chunks, sector_briefs=sector_briefs
    )


__all__ = ["router"]
