"""Phase 6 — per-run observability aggregation endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_runs import ResearchRun
from app.schemas.observability import RunCostLedger, RunEvidenceFlow, RunGraph
from app.services.observability import (
    aggregate_cost_ledger,
    aggregate_evidence_flow,
    aggregate_run_graph,
)

router = APIRouter()


async def _require_run(session: SessionDep, run_id: uuid.UUID) -> None:
    run = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="research run not found",
        )


@router.get(
    "/research-runs/{run_id}/cost-ledger",
    response_model=RunCostLedger,
)
async def get_run_cost_ledger(
    run_id: uuid.UUID, session: SessionDep
) -> RunCostLedger:
    await _require_run(session=session, run_id=run_id)
    return await aggregate_cost_ledger(session=session, run_id=run_id)


@router.get(
    "/research-runs/{run_id}/evidence-flow",
    response_model=RunEvidenceFlow,
)
async def get_run_evidence_flow(
    run_id: uuid.UUID, session: SessionDep
) -> RunEvidenceFlow:
    await _require_run(session=session, run_id=run_id)
    return await aggregate_evidence_flow(session=session, run_id=run_id)


@router.get(
    "/research-runs/{run_id}/graph",
    response_model=RunGraph,
)
async def get_run_graph(run_id: uuid.UUID, session: SessionDep) -> RunGraph:
    await _require_run(session=session, run_id=run_id)
    return await aggregate_run_graph(session=session, run_id=run_id)


__all__ = ["router"]
