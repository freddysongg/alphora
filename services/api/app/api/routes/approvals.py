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
from sqlalchemy import desc, or_, select, update

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


async def _decide(
    *,
    session: SessionDep,
    approval_id: uuid.UUID,
    target_status: PendingApprovalStatus,
    identity: str,
    reject_reason: str | None,
) -> PendingApprovalPublic:
    """Conditional-update decide. Prevents stale-pending approval of an
    expired row (a row whose `expires_at` has passed but which the
    sweeper/runner has not yet flipped). The update only succeeds when
    the row is `pending` AND `expires_at` is null or in the future; on
    failure we resolve the actual state and return 404/422 accordingly.
    """
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "status": target_status.value,
        "decided_by": identity,
        "decided_at": now,
    }
    if target_status is PendingApprovalStatus.rejected:
        values["reject_reason"] = reject_reason
    result = await session.execute(
        update(PendingApprovalRow)
        .where(PendingApprovalRow.id == approval_id)
        .where(PendingApprovalRow.status == PendingApprovalStatus.pending.value)
        .where(
            or_(
                PendingApprovalRow.expires_at.is_(None),
                PendingApprovalRow.expires_at > now,
            )
        )
        .values(**values)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        existing = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == approval_id)
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="approval not found",
            )
        existing_expires_at = existing.expires_at
        if existing_expires_at is not None and existing_expires_at.tzinfo is None:
            existing_expires_at = existing_expires_at.replace(tzinfo=UTC)
        if (
            existing.status == PendingApprovalStatus.pending.value
            and existing_expires_at is not None
            and existing_expires_at <= now
        ):
            await session.execute(
                update(PendingApprovalRow)
                .where(PendingApprovalRow.id == approval_id)
                .where(
                    PendingApprovalRow.status == PendingApprovalStatus.pending.value
                )
                .values(
                    status=PendingApprovalStatus.expired.value,
                    decided_by="auto",
                    decided_at=now,
                )
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "expired",
                    "current_status": PendingApprovalStatus.expired.value,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "already_decided",
                "current_status": existing.status,
            },
        )
    await session.commit()
    decided = await session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == approval_id)
    )
    assert decided is not None
    return PendingApprovalPublic.model_validate(decided)


@router.post("/{approval_id}/approve", response_model=PendingApprovalPublic)
async def approve(
    approval_id: uuid.UUID, session: SessionDep, identity: HumanTokenDep
) -> PendingApprovalPublic:
    return await _decide(
        session=session,
        approval_id=approval_id,
        target_status=PendingApprovalStatus.approved,
        identity=identity,
        reject_reason=None,
    )


@router.post("/{approval_id}/reject", response_model=PendingApprovalPublic)
async def reject(
    approval_id: uuid.UUID,
    session: SessionDep,
    identity: HumanTokenDep,
    payload: ApprovalRejectPayload | None = None,
) -> PendingApprovalPublic:
    return await _decide(
        session=session,
        approval_id=approval_id,
        target_status=PendingApprovalStatus.rejected,
        identity=identity,
        reject_reason=payload.reject_reason if payload is not None else None,
    )


__all__ = ["router"]
