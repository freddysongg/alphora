"""Phase 7 HITL approval queue API (spec §10.3).

Endpoints:
  GET    /approvals                  list (status + mode filters)
  GET    /approvals/{id}             detail (embeds judge verdict)
  POST   /approvals/{id}/approve     human action, token-gated (Task 9)
  POST   /approvals/{id}/reject      human action, token-gated (Task 9)
"""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import SessionDep
from app.db.models_approval import PendingApprovalRow
from app.db.models_judge import JudgeVerdictRow
from app.schemas.approvals import (
    JudgeVerdictSummary,
    PendingApprovalDetail,
    PendingApprovalPublic,
)

router = APIRouter()

ApprovalStatusFilter = Literal["pending", "approved", "rejected", "expired"]
ApprovalModeFilter = Literal["paper", "live"]


@router.get("", response_model=list[PendingApprovalPublic])
async def list_approvals(
    session: SessionDep,
    status_: Annotated[ApprovalStatusFilter | None, Query(alias="status")] = None,
    mode: ApprovalModeFilter | None = None,
) -> list[PendingApprovalPublic]:
    stmt = select(PendingApprovalRow).order_by(desc(PendingApprovalRow.created_at))
    if status_ is not None:
        stmt = stmt.where(PendingApprovalRow.status == status_)
    if mode is not None:
        stmt = stmt.where(PendingApprovalRow.mode == mode)
    rows = (await session.execute(stmt)).scalars().all()
    return [PendingApprovalPublic.model_validate(row) for row in rows]


@router.get("/{approval_id}", response_model=PendingApprovalDetail)
async def get_approval(
    approval_id: uuid.UUID, session: SessionDep
) -> PendingApprovalDetail:
    row = await session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == approval_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval not found"
        )
    verdict: JudgeVerdictSummary | None = None
    if row.judge_verdict_id is not None:
        verdict_row = await session.scalar(
            select(JudgeVerdictRow).where(JudgeVerdictRow.id == row.judge_verdict_id)
        )
        if verdict_row is not None:
            verdict = JudgeVerdictSummary.model_validate(verdict_row)
    base = PendingApprovalPublic.model_validate(row)
    return PendingApprovalDetail(**base.model_dump(), judge_verdict=verdict)


__all__ = ["router"]
