from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_judge import JudgeDecisionDb, JudgeVerdictRow
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)


def test_pending_approval_status_enum_values() -> None:
    assert PendingApprovalStatus.pending.value == "pending"
    assert PendingApprovalStatus.approved.value == "approved"
    assert PendingApprovalStatus.rejected.value == "rejected"
    assert PendingApprovalStatus.expired.value == "expired"
    assert {m.value for m in PendingApprovalStatus} == {
        "pending",
        "approved",
        "rejected",
        "expired",
    }


@pytest.mark.asyncio
async def test_pending_approval_persists_full_row(
    db_session: AsyncSession,
) -> None:
    run = StrategyRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        mode=StrategyRunMode.live.value,
        status=StrategyRunStatus.running.value,
        params={},
    )
    db_session.add(run)
    await db_session.flush()

    expires = datetime(2026, 5, 25, 18, 0, tzinfo=UTC)
    row = PendingApprovalRow(
        id=uuid.uuid4(),
        run_id=run.id,
        judge_verdict_id=None,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("3.5"),
        estimated_fill_price=Decimal("100.25"),
        mode="live",
        status=PendingApprovalStatus.pending.value,
        decided_by=None,
        decided_at=None,
        reject_reason=None,
        expires_at=expires,
    )
    db_session.add(row)
    await db_session.commit()

    fetched = await db_session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == row.id)
    )
    assert fetched is not None
    assert fetched.run_id == run.id
    assert fetched.mode == "live"
    assert fetched.status == "pending"
    assert fetched.qty == Decimal("3.5")
    assert fetched.expires_at == expires
    assert fetched.decided_by is None


@pytest.mark.asyncio
async def test_pending_approval_cascade_deletes_with_run(
    db_session: AsyncSession,
) -> None:
    run = StrategyRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        mode=StrategyRunMode.paper.value,
        status=StrategyRunStatus.stopped.value,
        params={},
    )
    db_session.add(run)
    await db_session.flush()
    row = PendingApprovalRow(
        id=uuid.uuid4(),
        run_id=run.id,
        judge_verdict_id=None,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="paper",
        status=PendingApprovalStatus.approved.value,
        decided_by="auto",
        decided_at=datetime.now(UTC),
        reject_reason=None,
        expires_at=None,
    )
    db_session.add(row)
    await db_session.commit()

    await db_session.delete(run)
    await db_session.commit()

    survivor = await db_session.scalar(
        select(PendingApprovalRow).where(PendingApprovalRow.id == row.id)
    )
    assert survivor is None


@pytest.mark.asyncio
async def test_pending_approval_set_null_on_verdict_delete(
    db_session: AsyncSession,
) -> None:
    run = StrategyRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        mode=StrategyRunMode.live.value,
        status=StrategyRunStatus.running.value,
        params={},
    )
    db_session.add(run)
    await db_session.flush()
    verdict = JudgeVerdictRow(
        id=uuid.uuid4(),
        run_id=run.id,
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
    db_session.add(verdict)
    await db_session.flush()
    row = PendingApprovalRow(
        id=uuid.uuid4(),
        run_id=run.id,
        judge_verdict_id=verdict.id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="live",
        status=PendingApprovalStatus.pending.value,
        decided_by=None,
        decided_at=None,
        reject_reason=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db_session.add(row)
    await db_session.commit()

    await db_session.delete(verdict)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.judge_verdict_id is None
    assert row.status == "pending"
