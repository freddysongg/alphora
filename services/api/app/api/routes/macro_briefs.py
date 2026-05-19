import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun
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
    chunk_ids = list({claim.chunk_id for claim in brief.cited_claims})
    chunks: list[ChunkLookup] = []
    if chunk_ids:
        chunk_rows = (
            await session.execute(
                select(EvidenceChunk, Evidence.source)
                .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
                .where(EvidenceChunk.id.in_(chunk_ids))
            )
        ).all()
        for chunk_row, source in chunk_rows:
            chunks.append(
                ChunkLookup(
                    chunk_id=chunk_row.id,
                    evidence_id=chunk_row.evidence_id,
                    source=source,
                    text=chunk_row.text,
                    attributes=chunk_row.attributes or {},
                )
            )

    return MacroBriefPublic(brief=brief, chunks=chunks)


__all__ = ["router"]
