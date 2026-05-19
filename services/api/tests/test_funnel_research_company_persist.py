import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import Entity, EntityType
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.company_thesis import CompanyThesis
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import JudgePublic, JudgeStatus
from app.services.strategies.funnel_research.company.persist import (
    persist_company_thesis,
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


async def _seed_entity(
    session: AsyncSession, *, type: EntityType, name: str
) -> uuid.UUID:
    entity = Entity(
        type=type.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.commit()
    return entity.id


def _thesis(
    *,
    company_entity_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
) -> CompanyThesis:
    return CompanyThesis(
        company_entity_id=company_entity_id,
        company_name="Apple Inc.",
        sector_entity_id=sector_entity_id,
        sector_name="Information Technology",
        ticker="AAPL",
        direction=SectorCallDirection.overweight,
        conviction=0.85,
        bull_case="Strong fundamentals",
        bear_case="Demand risks",
        catalysts=[],
        risks=[],
        cited_claims=[],
        confidence=0.7,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


@pytest.mark.asyncio
async def test_persist_company_thesis_writes_row(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session)
    company_id = await _seed_entity(
        db_session, type=EntityType.company, name="Apple Inc."
    )
    sector_id = await _seed_entity(
        db_session, type=EntityType.sector, name="Information Technology"
    )
    thesis = _thesis(company_entity_id=company_id, sector_entity_id=sector_id)
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)

    row_id = await persist_company_thesis(
        session=db_session,
        run_id=run_id,
        thesis=thesis,
        judge=judge,
        wall_clock_ms=4321,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(CompanyThesisRow).where(CompanyThesisRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.direction == "overweight"
    assert loaded.ticker == "AAPL"
    assert loaded.judge_status == "not_run"
    assert loaded.regeneration_count == 0
    assert loaded.wall_clock_ms == 4321
    payload = loaded.payload
    assert isinstance(payload, dict)
    assert payload["company_name"] == "Apple Inc."


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


@pytest.mark.asyncio
async def test_persist_company_thesis_writes_judge_flagged(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    company_id = await _seed_entity(
        db_session, type=EntityType.company, name="Apple Inc."
    )
    sector_id = await _seed_entity(
        db_session, type=EntityType.sector, name="Information Technology"
    )
    call_id = await _seed_llm_call_log(db_session, run_id)
    judge = JudgePublic(
        status=JudgeStatus.flagged,
        reasons=["contradiction"],
        call_id=call_id,
    )

    row_id = await persist_company_thesis(
        session=db_session,
        run_id=run_id,
        thesis=_thesis(company_entity_id=company_id, sector_entity_id=sector_id),
        judge=judge,
        wall_clock_ms=100,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(CompanyThesisRow).where(CompanyThesisRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.judge_status == "flagged"
    assert loaded.judge_reasons == ["contradiction"]
    assert loaded.judge_call_id == call_id


@pytest.mark.asyncio
async def test_persist_company_thesis_unique_per_run_and_company(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    company_id = await _seed_entity(
        db_session, type=EntityType.company, name="Apple Inc."
    )
    sector_id = await _seed_entity(
        db_session, type=EntityType.sector, name="Information Technology"
    )
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)

    await persist_company_thesis(
        session=db_session,
        run_id=run_id,
        thesis=_thesis(company_entity_id=company_id, sector_entity_id=sector_id),
        judge=judge,
        wall_clock_ms=10,
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await persist_company_thesis(
            session=db_session,
            run_id=run_id,
            thesis=_thesis(company_entity_id=company_id, sector_entity_id=sector_id),
            judge=judge,
            wall_clock_ms=20,
        )
