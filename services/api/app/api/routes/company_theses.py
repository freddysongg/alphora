import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_runs import ResearchRun
from app.schemas.company_thesis import CompanyThesis, CompanyThesisPublic
from app.schemas.sector_brief import JudgePublic, JudgeStatus

router = APIRouter()


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
    return CompanyThesisPublic(thesis=thesis, judge=judge)


__all__ = ["router"]
