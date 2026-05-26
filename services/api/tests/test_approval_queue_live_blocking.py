"""Live-mode request_approval blocks until an external actor flips status."""
from __future__ import annotations

import asyncio
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
                mode=StrategyRunMode.live.value,
                status=StrategyRunStatus.running.value,
                params={},
            )
        )
        await session.commit()
    return run_id


def _request(run_id: uuid.UUID) -> ApprovalRequest:
    return ApprovalRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="live",
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=None,
    )


async def _flip_status(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    pending_id: uuid.UUID,
    status: str,
    decided_by: str,
    reject_reason: str | None = None,
    delay_seconds: float = 0.1,
) -> None:
    await asyncio.sleep(delay_seconds)
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == pending_id)
        )
        assert row is not None
        row.status = status
        row.decided_by = decided_by
        row.decided_at = datetime.now(UTC)
        row.reject_reason = reject_reason
        await session.commit()


@pytest.mark.asyncio
async def test_live_request_blocks_until_external_approve(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)

    async def _flip_when_pending() -> None:
        deadline = datetime.now(UTC).timestamp() + 5
        while True:
            async with session_maker() as session:
                row = await session.scalar(
                    select(PendingApprovalRow).where(
                        PendingApprovalRow.run_id == run_id,
                        PendingApprovalRow.status
                        == PendingApprovalStatus.pending.value,
                    )
                )
            if row is not None:
                await _flip_status(
                    session_maker,
                    pending_id=row.id,
                    status=PendingApprovalStatus.approved.value,
                    decided_by="human:default",
                    delay_seconds=0.0,
                )
                return
            if datetime.now(UTC).timestamp() > deadline:
                raise AssertionError("no pending row appeared")
            await asyncio.sleep(0.02)

    flip_task = asyncio.create_task(_flip_when_pending())
    decision = await request_approval(
        _request(run_id),
        session_maker=session_maker,
        poll_interval_seconds=0.05,
        live_expires_after_seconds=10.0,
    )
    await flip_task
    assert decision.decision == "approved"
    assert decision.decided_by == "human:default"


@pytest.mark.asyncio
async def test_live_request_returns_rejected_with_reason(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)

    async def _flip() -> None:
        deadline = datetime.now(UTC).timestamp() + 5
        while True:
            async with session_maker() as session:
                row = await session.scalar(
                    select(PendingApprovalRow).where(
                        PendingApprovalRow.run_id == run_id,
                        PendingApprovalRow.status
                        == PendingApprovalStatus.pending.value,
                    )
                )
            if row is not None:
                await _flip_status(
                    session_maker,
                    pending_id=row.id,
                    status=PendingApprovalStatus.rejected.value,
                    decided_by="human:default",
                    reject_reason="thesis weakened",
                    delay_seconds=0.0,
                )
                return
            if datetime.now(UTC).timestamp() > deadline:
                raise AssertionError("no pending row appeared")
            await asyncio.sleep(0.02)

    flip_task = asyncio.create_task(_flip())
    decision = await request_approval(
        _request(run_id),
        session_maker=session_maker,
        poll_interval_seconds=0.05,
        live_expires_after_seconds=10.0,
    )
    await flip_task
    assert decision.decision == "rejected"
    assert decision.reject_reason == "thesis weakened"
    assert decision.decided_by == "human:default"
