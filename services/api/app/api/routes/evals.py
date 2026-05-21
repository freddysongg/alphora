"""Phase 2 — counterfactual + leakage observability routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import SessionDep
from app.db.models_evals import (
    CounterfactualGateRun,
    CounterfactualPerturbation,
    LeakageHoldoutCase,
    LeakageRun,
)
from app.db.models_runs import ResearchRun
from app.schemas.evals import (
    CounterfactualGateRunPublic,
    CounterfactualPerturbationPublic,
    CounterfactualRunSummary,
    LeakageHoldoutCaseInput,
    LeakageHoldoutCasePublic,
    LeakageRunPublic,
    LeakageRunRequest,
)
from app.services.evals.leakage import (
    persist_holdout_case,
    persist_leakage_run,
)

router = APIRouter()

_PERTURBATION_LIMIT_MAX: int = 200
_LEAKAGE_LIST_LIMIT_MAX: int = 200


@router.get(
    "/research-runs/{run_id}/counterfactuals",
    response_model=CounterfactualRunSummary,
)
async def get_run_counterfactuals(
    run_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=_PERTURBATION_LIMIT_MAX)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CounterfactualRunSummary:
    run = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="research run not found"
        )
    gate_rows = (
        (
            await session.execute(
                select(CounterfactualGateRun)
                .where(CounterfactualGateRun.run_id == run_id)
                .order_by(CounterfactualGateRun.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    perturbation_rows = (
        (
            await session.execute(
                select(CounterfactualPerturbation)
                .where(CounterfactualPerturbation.run_id == run_id)
                .order_by(desc(CounterfactualPerturbation.created_at))
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return CounterfactualRunSummary(
        gates=[CounterfactualGateRunPublic.model_validate(g) for g in gate_rows],
        perturbations=[
            CounterfactualPerturbationPublic.model_validate(p)
            for p in perturbation_rows
        ],
    )


@router.post(
    "/evals/leakage/cases",
    response_model=LeakageHoldoutCasePublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_leakage_case(
    payload: LeakageHoldoutCaseInput,
    session: SessionDep,
) -> LeakageHoldoutCasePublic:
    row = await persist_holdout_case(
        session=session,
        case_name=payload.case_name,
        cutoff_at=payload.cutoff_at,
        full_decision=payload.full_decision,
        restricted_decision=payload.restricted_decision,
    )
    await session.commit()
    return LeakageHoldoutCasePublic.model_validate(row)


@router.get(
    "/evals/leakage/cases",
    response_model=list[LeakageHoldoutCasePublic],
)
async def list_leakage_cases(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=_LEAKAGE_LIST_LIMIT_MAX)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LeakageHoldoutCasePublic]:
    rows = (
        (
            await session.execute(
                select(LeakageHoldoutCase)
                .order_by(desc(LeakageHoldoutCase.created_at))
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [LeakageHoldoutCasePublic.model_validate(r) for r in rows]


@router.post(
    "/evals/leakage/runs",
    response_model=LeakageRunPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_leakage_run(
    payload: LeakageRunRequest,
    session: SessionDep,
) -> LeakageRunPublic:
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
    case_rows = (
        (
            await session.execute(
                select(LeakageHoldoutCase).where(
                    LeakageHoldoutCase.id.in_(payload.case_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if len(case_rows) != len(set(payload.case_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="one or more leakage cases not found",
        )
    row, _outcome = await persist_leakage_run(
        session=session,
        run_id=payload.run_id,
        cases=case_rows,
    )
    await session.commit()
    return LeakageRunPublic.model_validate(row)


@router.get(
    "/evals/leakage/runs",
    response_model=list[LeakageRunPublic],
)
async def list_leakage_runs(
    session: SessionDep,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_LEAKAGE_LIST_LIMIT_MAX)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LeakageRunPublic]:
    stmt = select(LeakageRun).order_by(desc(LeakageRun.created_at))
    if run_id is not None:
        stmt = stmt.where(LeakageRun.run_id == run_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [LeakageRunPublic.model_validate(r) for r in rows]


__all__ = ["router"]
