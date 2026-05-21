import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorCompanyIdea,
)
from app.services.strategies.funnel_research.sector.persist import (
    persist_sector_brief,
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


async def _seed_sector_entity(session: AsyncSession) -> uuid.UUID:
    entity = Entity(
        type=EntityType.sector.value,
        canonical_name="Information Technology",
        aliases=[],
        external_ids={"gics_code": "45"},
        attributes={"gics_level": 1, "gics_code": "45"},
    )
    session.add(entity)
    await session.commit()
    return entity.id


def _brief(sector_id: uuid.UUID) -> SectorBrief:
    return SectorBrief(
        sector_entity_id=sector_id,
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        themes=[],
        companies=[
            SectorCompanyIdea(
                name="AAPL",
                ticker="AAPL",
                direction=SectorCallDirection.overweight,
                conviction=0.7,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        watch_items=[],
        cited_claims=[],
        confidence=0.75,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


@pytest.mark.asyncio
async def test_persist_sector_brief_writes_row(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session)
    sector_id = await _seed_sector_entity(db_session)
    brief = _brief(sector_id)
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)

    row_id = await persist_sector_brief(
        session=db_session,
        run_id=run_id,
        brief=brief,
        judge=judge,
        wall_clock_ms=1234,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(SectorBriefRow).where(SectorBriefRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.direction == "overweight"
    assert loaded.judge_status == "not_run"
    assert loaded.regeneration_count == 0
    assert loaded.wall_clock_ms == 1234
    payload = loaded.payload
    assert isinstance(payload, dict)
    assert payload["sector_name"] == "Information Technology"


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
async def test_persist_sector_brief_writes_judge_flagged(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_id = await _seed_sector_entity(db_session)
    call_id = await _seed_llm_call_log(db_session, run_id)
    judge = JudgePublic(
        status=JudgeStatus.flagged,
        reasons=["contradiction"],
        call_id=call_id,
    )

    row_id = await persist_sector_brief(
        session=db_session,
        run_id=run_id,
        brief=_brief(sector_id),
        judge=judge,
        wall_clock_ms=100,
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(SectorBriefRow).where(SectorBriefRow.id == row_id)
        )
    ).scalar_one()
    assert loaded.judge_status == "flagged"
    assert loaded.judge_reasons == ["contradiction"]
    assert loaded.judge_call_id == call_id


@pytest.mark.asyncio
async def test_persist_sector_brief_unique_per_run_and_sector(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_id = await _seed_sector_entity(db_session)
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)

    await persist_sector_brief(
        session=db_session,
        run_id=run_id,
        brief=_brief(sector_id),
        judge=judge,
        wall_clock_ms=10,
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await persist_sector_brief(
            session=db_session,
            run_id=run_id,
            brief=_brief(sector_id),
            judge=judge,
            wall_clock_ms=20,
        )
