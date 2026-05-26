"""Phase 7 HITL approval queue API (spec §10.3).

Endpoints:
  GET    /approvals                  list (status + mode filters)
  GET    /approvals/{id}             detail (embeds judge verdict)
  POST   /approvals/{id}/approve     human action, token-gated (Task 9)
  POST   /approvals/{id}/reject      human action, token-gated (Task 9)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import HumanTokenDep, SessionDep
from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_judge import JudgeVerdictRow
from app.schemas.approvals import (
    ApprovalRejectPayload,
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


@router.post("/{approval_id}/approve", response_model=PendingApprovalPublic)
async def approve(
    approval_id: uuid.UUID, session: SessionDep, identity: HumanTokenDep
) -> PendingApprovalPublic:
    row = await session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == approval_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval not found"
        )
    if row.status != PendingApprovalStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "already_decided",
                "current_status": row.status,
            },
        )
    row.status = PendingApprovalStatus.approved.value
    row.decided_by = identity
    row.decided_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
    return PendingApprovalPublic.model_validate(row)


@router.post("/{approval_id}/reject", response_model=PendingApprovalPublic)
async def reject(
    approval_id: uuid.UUID,
    session: SessionDep,
    identity: HumanTokenDep,
    payload: ApprovalRejectPayload | None = None,
) -> PendingApprovalPublic:
    row = await session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == approval_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval not found"
        )
    if row.status != PendingApprovalStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "already_decided",
                "current_status": row.status,
            },
        )
    row.status = PendingApprovalStatus.rejected.value
    row.decided_by = identity
    row.decided_at = datetime.now(UTC)
    row.reject_reason = (payload.reject_reason if payload is not None else None)
    await session.commit()
    await session.refresh(row)
    return PendingApprovalPublic.model_validate(row)


__all__ = ["router"]
