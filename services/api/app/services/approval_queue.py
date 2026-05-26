"""Approval queue (spec sections 4.5, 4.6, and 9).

Phase 7 makes the queue real: every order writes a `pending_approvals`
row. Paper rows are inserted with `status=approved, decided_by="auto"`
when `auto_approve_after_seconds == 0` (default); a non-zero delay
inserts pending, sleeps, then flips. Live rows insert pending and poll
the DB until the status changes (Task 6).

`ApprovalRequest` / `ApprovalDecision` are the persistence-aligned wire
shapes. The runner constructs `ApprovalRequest` after the judge has
returned a verdict; the queue returns an `ApprovalDecision` whose
`decision` field drives the runner's next step.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.services.llm_judge import JudgeDecision

ApprovalStatus = Literal["approved", "rejected", "expired"]

_AUTO_APPROVE_DECIDED_BY = "auto"


@dataclass(frozen=True)
class ApprovalRequest:
    """Input to the queue. The runner passes one of these per order."""

    run_id: uuid.UUID
    strategy_key: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: Decimal
    estimated_fill_price: Decimal
    mode: Literal["paper", "live"]
    judge_decision: JudgeDecision
    judge_size_multiplier: float | None
    judge_verdict_id: uuid.UUID | None


@dataclass(frozen=True)
class ApprovalDecision:
    """Outcome. `decided_by` is "auto" for paper, "human:<user_id>" for
    live (Phase 7). `decided_at` is when the decision was recorded.

    `pending_approval_id` is the id of the `pending_approvals` row that
    produced this decision. `reject_reason` carries the optional human
    explanation; auto-approve and approve paths leave it None.
    """

    decision: ApprovalStatus
    decided_by: str
    decided_at: datetime
    pending_approval_id: uuid.UUID
    reject_reason: str | None = None


def _default_clock() -> datetime:
    return datetime.now(UTC)


async def request_approval(
    request: ApprovalRequest,
    *,
    session_maker: Callable[[], AsyncSession],
    auto_approve_after_seconds: float = 0.0,
    live_expires_after_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
    clock: Callable[[], datetime] = _default_clock,
) -> ApprovalDecision:
    """Persist the request and resolve to a decision.

    Paper mode:
      - delay == 0  -> insert status=approved inline, return.
      - delay  > 0  -> insert pending, asyncio.sleep, flip inline.
    Live mode:
      - insert pending with expires_at, poll until status changes
        (Task 6).
    """
    pending_id = uuid.uuid4()
    now = clock()

    if request.mode == "paper":
        return await _handle_paper(
            request,
            session_maker=session_maker,
            pending_id=pending_id,
            now=now,
            auto_approve_after_seconds=auto_approve_after_seconds,
            clock=clock,
        )

    expires_at = now + timedelta(seconds=live_expires_after_seconds)
    return await _handle_live(
        request,
        session_maker=session_maker,
        pending_id=pending_id,
        now=now,
        expires_at=expires_at,
        poll_interval_seconds=poll_interval_seconds,
        clock=clock,
    )


async def _handle_paper(
    request: ApprovalRequest,
    *,
    session_maker: Callable[[], AsyncSession],
    pending_id: uuid.UUID,
    now: datetime,
    auto_approve_after_seconds: float,
    clock: Callable[[], datetime],
) -> ApprovalDecision:
    if auto_approve_after_seconds <= 0:
        async with session_maker() as session:
            session.add(
                PendingApprovalRow(
                    id=pending_id,
                    run_id=request.run_id,
                    judge_verdict_id=request.judge_verdict_id,
                    strategy_key=request.strategy_key,
                    ticker=request.ticker,
                    side=request.side,
                    qty=request.qty,
                    estimated_fill_price=request.estimated_fill_price,
                    mode=request.mode,
                    status=PendingApprovalStatus.approved.value,
                    decided_by=_AUTO_APPROVE_DECIDED_BY,
                    decided_at=now,
                    reject_reason=None,
                    expires_at=None,
                )
            )
            await session.commit()
        return ApprovalDecision(
            decision="approved",
            decided_by=_AUTO_APPROVE_DECIDED_BY,
            decided_at=now,
            pending_approval_id=pending_id,
        )

    async with session_maker() as session:
        session.add(
            PendingApprovalRow(
                id=pending_id,
                run_id=request.run_id,
                judge_verdict_id=request.judge_verdict_id,
                strategy_key=request.strategy_key,
                ticker=request.ticker,
                side=request.side,
                qty=request.qty,
                estimated_fill_price=request.estimated_fill_price,
                mode=request.mode,
                status=PendingApprovalStatus.pending.value,
                decided_by=None,
                decided_at=None,
                reject_reason=None,
                expires_at=None,
            )
        )
        await session.commit()

    await asyncio.sleep(auto_approve_after_seconds)
    flipped_at = clock()
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == pending_id)
        )
        if row is None:
            raise RuntimeError(
                f"pending_approvals row {pending_id} vanished after insert"
            )
        if row.status == PendingApprovalStatus.pending.value:
            row.status = PendingApprovalStatus.approved.value
            row.decided_by = _AUTO_APPROVE_DECIDED_BY
            row.decided_at = flipped_at
            await session.commit()
        return ApprovalDecision(
            decision=row.status,  # type: ignore[arg-type]
            decided_by=row.decided_by or _AUTO_APPROVE_DECIDED_BY,
            decided_at=row.decided_at or flipped_at,
            pending_approval_id=pending_id,
            reject_reason=row.reject_reason,
        )


async def _handle_live(
    request: ApprovalRequest,
    *,
    session_maker: Callable[[], AsyncSession],
    pending_id: uuid.UUID,
    now: datetime,
    expires_at: datetime,
    poll_interval_seconds: float,
    clock: Callable[[], datetime],
) -> ApprovalDecision:
    async with session_maker() as session:
        session.add(
            PendingApprovalRow(
                id=pending_id,
                run_id=request.run_id,
                judge_verdict_id=request.judge_verdict_id,
                strategy_key=request.strategy_key,
                ticker=request.ticker,
                side=request.side,
                qty=request.qty,
                estimated_fill_price=request.estimated_fill_price,
                mode=request.mode,
                status=PendingApprovalStatus.pending.value,
                decided_by=None,
                decided_at=None,
                reject_reason=None,
                expires_at=expires_at,
            )
        )
        await session.commit()

    while True:
        await asyncio.sleep(poll_interval_seconds)
        current_now = clock()
        async with session_maker() as session:
            row = await session.scalar(
                select(PendingApprovalRow).where(PendingApprovalRow.id == pending_id)
            )
            if row is None:
                raise RuntimeError(
                    f"pending_approvals row {pending_id} vanished while polling"
                )
            if row.status != PendingApprovalStatus.pending.value:
                return ApprovalDecision(
                    decision=row.status,  # type: ignore[arg-type]
                    decided_by=row.decided_by or "human:default",
                    decided_at=row.decided_at or current_now,
                    pending_approval_id=pending_id,
                    reject_reason=row.reject_reason,
                )
            if current_now >= expires_at:
                row.status = PendingApprovalStatus.expired.value
                row.decided_by = _AUTO_APPROVE_DECIDED_BY
                row.decided_at = current_now
                await session.commit()
                return ApprovalDecision(
                    decision="expired",
                    decided_by=_AUTO_APPROVE_DECIDED_BY,
                    decided_at=current_now,
                    pending_approval_id=pending_id,
                )


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
    "request_approval",
]
