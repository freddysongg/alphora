"""ApprovalExpirySweeper flips pending+live+overdue rows to expired."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from app.services.approval_expiry_sweeper import ApprovalExpirySweeper


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


async def _seed_pending(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    expires_at: datetime | None,
    mode: str = "live",
    status_val: str = "pending",
) -> uuid.UUID:
    pending_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(
            PendingApprovalRow(
                id=pending_id,
                run_id=run_id,
                judge_verdict_id=None,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                side="buy",
                qty=Decimal("1"),
                estimated_fill_price=Decimal("100"),
                mode=mode,
                status=status_val,
                decided_by=None if status_val == "pending" else "auto",
                decided_at=None if status_val == "pending" else datetime.now(UTC),
                reject_reason=None,
                expires_at=expires_at,
            )
        )
        await session.commit()
    return pending_id


@pytest.mark.asyncio
async def test_sweeper_flips_overdue_live_rows(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    now = datetime.now(UTC)
    overdue_id = await _seed_pending(
        session_maker, run_id=run_id, expires_at=now - timedelta(minutes=1)
    )
    fresh_id = await _seed_pending(
        session_maker, run_id=run_id, expires_at=now + timedelta(minutes=5)
    )
    sweeper = ApprovalExpirySweeper(
        session_factory=session_maker, interval_seconds=10.0, clock=lambda: now
    )
    report = await sweeper.run_once()
    assert overdue_id in report.expired_ids
    assert fresh_id not in report.expired_ids
    async with session_maker() as session:
        overdue = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == overdue_id)
        )
        fresh = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == fresh_id)
        )
    assert overdue is not None and overdue.status == PendingApprovalStatus.expired.value
    assert overdue.decided_by == "auto"
    assert overdue.decided_at is not None
    assert fresh is not None and fresh.status == PendingApprovalStatus.pending.value


@pytest.mark.asyncio
async def test_sweeper_ignores_non_live_rows(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    now = datetime.now(UTC)
    paper_id = await _seed_pending(
        session_maker,
        run_id=run_id,
        expires_at=now - timedelta(minutes=1),
        mode="paper",
    )
    sweeper = ApprovalExpirySweeper(
        session_factory=session_maker, interval_seconds=10.0, clock=lambda: now
    )
    report = await sweeper.run_once()
    assert paper_id not in report.expired_ids
    async with session_maker() as session:
        paper = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == paper_id)
        )
    assert paper is not None and paper.status == PendingApprovalStatus.pending.value


@pytest.mark.asyncio
async def test_sweeper_ignores_non_pending_rows(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    now = datetime.now(UTC)
    approved_id = await _seed_pending(
        session_maker,
        run_id=run_id,
        expires_at=now - timedelta(minutes=1),
        status_val="approved",
    )
    sweeper = ApprovalExpirySweeper(
        session_factory=session_maker, interval_seconds=10.0, clock=lambda: now
    )
    report = await sweeper.run_once()
    assert approved_id not in report.expired_ids
