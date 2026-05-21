"""Phase 2 — weekly human review API."""

import uuid
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import SessionDep
from app.db.models_evals import HumanReview
from app.db.models_runs import ResearchRun
from app.schemas.evals import (
    BriefKindEnum,
    HumanReviewInput,
    HumanReviewPublic,
    HumanReviewSummary,
    HumanReviewWeekSummary,
)

router = APIRouter()

_REVIEW_LIST_LIMIT_MAX: int = 200
_DEFAULT_SUMMARY_WEEKS: int = 12
_SUMMARY_WEEKS_MAX: int = 52


@router.post(
    "/human-reviews",
    response_model=HumanReviewPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_human_review(
    payload: HumanReviewInput,
    session: SessionDep,
) -> HumanReviewPublic:
    if payload.run_id is not None:
        run = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == payload.run_id)
            )
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="research run not found"
            )
    row = HumanReview(
        run_id=payload.run_id,
        brief_kind=payload.brief_kind.value if payload.brief_kind is not None else None,
        week_start=payload.week_start,
        reviewer=payload.reviewer,
        surfaced_missed=payload.surfaced_missed,
        missed_noticed=payload.missed_noticed,
        notes=payload.notes,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return HumanReviewPublic.model_validate(row)


@router.get(
    "/human-reviews",
    response_model=list[HumanReviewPublic],
)
async def list_human_reviews(
    session: SessionDep,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
    week_start: Annotated[date | None, Query()] = None,
    brief_kind: Annotated[BriefKindEnum | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_REVIEW_LIST_LIMIT_MAX)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[HumanReviewPublic]:
    stmt = select(HumanReview).order_by(desc(HumanReview.created_at))
    if run_id is not None:
        stmt = stmt.where(HumanReview.run_id == run_id)
    if week_start is not None:
        stmt = stmt.where(HumanReview.week_start == week_start)
    if brief_kind is not None:
        stmt = stmt.where(HumanReview.brief_kind == brief_kind.value)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [HumanReviewPublic.model_validate(r) for r in rows]


@router.get(
    "/human-reviews/summary",
    response_model=HumanReviewSummary,
)
async def get_human_review_summary(
    session: SessionDep,
    weeks: Annotated[int, Query(ge=1, le=_SUMMARY_WEEKS_MAX)] = _DEFAULT_SUMMARY_WEEKS,
) -> HumanReviewSummary:
    rows = (
        (
            await session.execute(
                select(HumanReview).order_by(desc(HumanReview.week_start))
            )
        )
        .scalars()
        .all()
    )
    by_week: dict[date, list[HumanReview]] = defaultdict(list)
    for row in rows:
        by_week[row.week_start].append(row)
    ordered_weeks = sorted(by_week.keys(), reverse=True)[:weeks]
    week_summaries: list[HumanReviewWeekSummary] = []
    for week in ordered_weeks:
        entries = by_week[week]
        if not entries:
            continue
        review_count = len(entries)
        mean_surfaced = sum(e.surfaced_missed for e in entries) / review_count
        mean_missed = sum(e.missed_noticed for e in entries) / review_count
        week_summaries.append(
            HumanReviewWeekSummary(
                week_start=week,
                review_count=review_count,
                mean_surfaced_missed=mean_surfaced,
                mean_missed_noticed=mean_missed,
            )
        )
    return HumanReviewSummary(weeks=week_summaries)


__all__ = ["router"]
