from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_judge import JudgeDecisionDb, JudgeVerdictRow
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)


def test_judge_decision_db_enum_values() -> None:
    assert JudgeDecisionDb.approve.value == "approve"
    assert JudgeDecisionDb.veto.value == "veto"
    assert JudgeDecisionDb.approve_reduced.value == "approve_reduced"
    assert {m.value for m in JudgeDecisionDb} == {
        "approve",
        "veto",
        "approve_reduced",
    }


@pytest.mark.asyncio
async def test_judge_verdict_persists_full_row(db_session: AsyncSession) -> None:
    run = StrategyRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        mode=StrategyRunMode.paper.value,
        status=StrategyRunStatus.running.value,
        params={},
    )
    db_session.add(run)
    await db_session.flush()

    verdict = JudgeVerdictRow(
        id=uuid.uuid4(),
        run_id=run.id,
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
        ticker="SPY",
        strategy_key="macd_rsi_adx",
        side="buy",
        proposed_qty=Decimal("10"),
        decision=JudgeDecisionDb.approve_reduced.value,
        size_multiplier=0.5,
        reasoning_md="thin context, halving size",
        context_payload={"hypotheses": [], "company_thesis": None},
        llm_model="gpt-4o-mini",
        prompt_version="v1",
        llm_call_log_id=None,
    )
    db_session.add(verdict)
    await db_session.commit()

    fetched = await db_session.scalar(
        select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.id)
    )
    assert fetched is not None
    assert fetched.run_id == run.id
    assert fetched.decision == "approve_reduced"
    assert fetched.size_multiplier == 0.5
    assert fetched.context_payload == {"hypotheses": [], "company_thesis": None}
    assert fetched.prompt_version == "v1"


@pytest.mark.asyncio
async def test_judge_verdict_cascade_deletes_with_run(
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

    verdict = JudgeVerdictRow(
        id=uuid.uuid4(),
        run_id=run.id,
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
        ticker="SPY",
        strategy_key="macd_rsi_adx",
        side="buy",
        proposed_qty=Decimal("1"),
        decision=JudgeDecisionDb.veto.value,
        size_multiplier=None,
        reasoning_md="x",
        context_payload={},
        llm_model=None,
        prompt_version="v1",
        llm_call_log_id=None,
    )
    db_session.add(verdict)
    await db_session.commit()

    await db_session.delete(run)
    await db_session.commit()

    survivor = await db_session.scalar(
        select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.id)
    )
    assert survivor is None
