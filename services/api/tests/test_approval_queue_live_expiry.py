"""Live-mode self-detected expiry: the runner detects expires_at <= clock()."""
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


@pytest.mark.asyncio
async def test_live_request_self_expires(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(session_maker)
    decision = await request_approval(
        ApprovalRequest(
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
        ),
        session_maker=session_maker,
        poll_interval_seconds=0.02,
        live_expires_after_seconds=0.05,
    )
    assert decision.decision == "expired"
    assert decision.decided_by == "auto"
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(
                PendingApprovalRow.id == decision.pending_approval_id
            )
        )
    assert row is not None
    assert row.status == PendingApprovalStatus.expired.value
    assert row.decided_at is not None


@pytest.mark.asyncio
async def test_live_request_returns_expired_when_external_sweeper_flips_first(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """If the sweeper flips a row to expired before the runner's next poll
    detects expires_at <= now(), the runner observes status=expired
    and returns the expired decision without re-flipping the row.
    """
    run_id = await _seed_run(session_maker)

    async def _external_flip() -> None:
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
                async with session_maker() as session:
                    row = await session.scalar(
                        select(PendingApprovalRow).where(
                            PendingApprovalRow.id == row.id
                        )
                    )
                    assert row is not None
                    row.status = PendingApprovalStatus.expired.value
                    row.decided_by = "auto"
                    row.decided_at = datetime.now(UTC)
                    await session.commit()
                return
            if datetime.now(UTC).timestamp() > deadline:
                raise AssertionError("no pending row appeared")
            await asyncio.sleep(0.01)

    flip_task = asyncio.create_task(_external_flip())
    decision = await request_approval(
        ApprovalRequest(
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
        ),
        session_maker=session_maker,
        poll_interval_seconds=0.02,
        live_expires_after_seconds=60.0,
    )
    await flip_task
    assert decision.decision == "expired"
