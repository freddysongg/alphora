"""Paper-mode auto-approve writes a `status=approved` row and returns approved."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.approval_queue import (
    ApprovalDecision,
    ApprovalRequest,
    request_approval,
)


async def _seed_run(session_maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.running.value,
                params={},
            )
        )
        await session.commit()
    return run_id


def _request(run_id: uuid.UUID, *, mode: str = "paper") -> ApprovalRequest:
    return ApprovalRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode=mode,  # type: ignore[arg-type]
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=None,
    )


@pytest.mark.asyncio
async def test_paper_auto_approve_writes_row_with_status_approved(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    decision = await request_approval(
        _request(run_id),
        session_maker=session_maker,
        auto_approve_after_seconds=0.0,
    )
    assert decision.decision == "approved"
    assert decision.decided_by == "auto"
    assert isinstance(decision, ApprovalDecision)
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(
                PendingApprovalRow.id == decision.pending_approval_id
            )
        )
    assert row is not None
    assert row.status == PendingApprovalStatus.approved.value
    assert row.decided_by == "auto"
    assert row.mode == "paper"
    assert row.run_id == run_id


@pytest.mark.asyncio
async def test_paper_auto_approve_with_delay_sleeps_then_flips(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    start = datetime.now(UTC)
    decision = await request_approval(
        _request(run_id),
        session_maker=session_maker,
        auto_approve_after_seconds=0.05,
    )
    elapsed = (datetime.now(UTC) - start).total_seconds()
    assert decision.decision == "approved"
    assert decision.decided_by == "auto"
    assert elapsed >= 0.05
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(
                PendingApprovalRow.id == decision.pending_approval_id
            )
        )
    assert row is not None
    assert row.status == PendingApprovalStatus.approved.value


@pytest.mark.asyncio
async def test_paper_auto_approve_uses_supplied_judge_verdict_id(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When the request carries a judge_verdict_id, the row stores it."""
    from app.db.models_judge import JudgeDecisionDb, JudgeVerdictRow

    run_id = await _seed_run(session_maker)
    verdict_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(
            JudgeVerdictRow(
                id=verdict_id,
                run_id=run_id,
                bar_ts=datetime(2026, 5, 25, 14, 30, tzinfo=UTC),
                ticker="SPY",
                strategy_key="macd_rsi_adx",
                side="buy",
                proposed_qty=Decimal("1"),
                decision=JudgeDecisionDb.approve.value,
                size_multiplier=None,
                reasoning_md="ok",
                context_payload={},
                llm_model="gpt-4o-mini",
                prompt_version="v1",
                llm_call_log_id=None,
            )
        )
        await session.commit()
    request = ApprovalRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="paper",
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=verdict_id,
    )
    decision = await request_approval(
        request,
        session_maker=session_maker,
        auto_approve_after_seconds=0.0,
    )
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(
                PendingApprovalRow.id == decision.pending_approval_id
            )
        )
    assert row is not None
    assert row.judge_verdict_id == verdict_id
