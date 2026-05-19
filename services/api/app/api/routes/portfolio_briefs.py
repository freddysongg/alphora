import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import ResearchRun
from app.schemas.portfolio_brief import PortfolioBrief, PortfolioBriefPublic
from app.schemas.sector_brief import JudgePublic, JudgeStatus

router = APIRouter()


@router.get("/{run_id}/portfolio-brief", response_model=PortfolioBriefPublic)
async def get_portfolio_brief(
    run_id: uuid.UUID, session: SessionDep
) -> PortfolioBriefPublic:
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
            detail="portfolio brief not available for this strategy",
        )
    row = (
        await session.execute(
            select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="portfolio brief not yet available",
        )

    brief = PortfolioBrief.model_validate(row.payload)
    judge = JudgePublic(
        status=JudgeStatus(row.judge_status),
        reasons=list(row.judge_reasons or []),
        call_id=row.judge_call_id,
    )
    return PortfolioBriefPublic(brief=brief, judge=judge)


__all__ = ["router"]
