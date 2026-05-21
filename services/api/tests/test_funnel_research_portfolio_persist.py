import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.macro_brief import VerifierStatus
from app.schemas.portfolio_brief import (
    PortfolioBrief,
    PortfolioCoverage,
    PortfolioMacroSummary,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus
from app.services.strategies.funnel_research.portfolio.persist import (
    persist_portfolio_brief,
)


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_llm_call_log(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID:
    log = LlmCallLog(
        run_id=run_id,
        model="gpt-5-mini",
        prompt_hash="0" * 64,
        input_hash="0" * 64,
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        reasoning_tokens=0,
        cost_usd=Decimal("0.001"),
        latency_ms=12,
        status=LlmCallStatus.success,
    )
    session.add(log)
    await session.commit()
    return log.id


def _brief(run_id: uuid.UUID) -> PortfolioBrief:
    return PortfolioBrief(
        run_id=run_id,
        macro=PortfolioMacroSummary(
            themes=[],
            watch_items=[],
            confidence=0.6,
            judge_status=JudgeStatus.passed,
        ),
        sectors=[],
        companies=[],
        cited_claims=[],
        cited_chunk_ids=[],
        coverage=PortfolioCoverage(
            sectors_selected=0,
            sectors_verified=0,
            sectors_judge_passed=0,
            sectors_judge_flagged=0,
            companies_selected=0,
            companies_verified=0,
            companies_judge_passed=0,
            companies_judge_flagged=0,
        ),
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


@pytest.mark.asyncio
async def test_persist_portfolio_brief_writes_row(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session)
    judge = JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None)

    row_id = await persist_portfolio_brief(
        session=db_session,
        run_id=run_id,
        brief=_brief(run_id),
        judge=judge,
        wall_clock_ms=42,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(PortfolioBriefRow).where(PortfolioBriefRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.verifier_status == "verified"
    assert loaded.judge_status == "passed"
    assert loaded.judge_reasons is None
    assert loaded.regeneration_count == 0
    assert loaded.wall_clock_ms == 42
    assert isinstance(loaded.payload, dict)
    assert loaded.payload["run_id"] == str(run_id)


@pytest.mark.asyncio
async def test_persist_portfolio_brief_writes_judge_flagged_with_reasons(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    call_id = await _seed_llm_call_log(db_session, run_id)
    judge = JudgePublic(
        status=JudgeStatus.flagged,
        reasons=["sector picks contradict macro"],
        call_id=call_id,
    )

    row_id = await persist_portfolio_brief(
        session=db_session,
        run_id=run_id,
        brief=_brief(run_id),
        judge=judge,
        wall_clock_ms=10,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(PortfolioBriefRow).where(PortfolioBriefRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.judge_status == "flagged"
    assert loaded.judge_reasons == ["sector picks contradict macro"]
    assert loaded.judge_call_id == call_id


@pytest.mark.asyncio
async def test_persist_portfolio_brief_unique_per_run(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)

    await persist_portfolio_brief(
        session=db_session,
        run_id=run_id,
        brief=_brief(run_id),
        judge=judge,
        wall_clock_ms=1,
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await persist_portfolio_brief(
            session=db_session,
            run_id=run_id,
            brief=_brief(run_id),
            judge=judge,
            wall_clock_ms=2,
        )
