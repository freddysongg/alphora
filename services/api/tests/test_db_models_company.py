import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis
from app.db.models_graph import Entity, EntityType
from app.db.models_runs import ResearchRun, RunStatus, Strategy


def _make_run() -> ResearchRun:
    return ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=dt.date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )


def _make_entity(*, entity_type: EntityType, name: str) -> Entity:
    return Entity(
        id=uuid.uuid4(),
        type=entity_type.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )


def _make_company_thesis(
    *,
    run_id: uuid.UUID,
    company_entity_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    direction: str = "overweight",
    verifier_status: str = "verified",
    judge_status: str = "not_run",
) -> CompanyThesis:
    return CompanyThesis(
        run_id=run_id,
        company_entity_id=company_entity_id,
        sector_entity_id=sector_entity_id,
        ticker="EXMP",
        direction=direction,
        payload={"company_entity_id": str(company_entity_id), "company_name": "Example"},
        verifier_status=verifier_status,
        regeneration_count=0,
        judge_status=judge_status,
        wall_clock_ms=1234,
    )


async def _seed_run_and_entities(
    db_session: AsyncSession,
) -> tuple[ResearchRun, Entity, Entity]:
    run = _make_run()
    company = _make_entity(entity_type=EntityType.company, name="Example Corp")
    sector = _make_entity(entity_type=EntityType.sector, name="Information Technology")
    db_session.add_all([run, company, sector])
    await db_session.flush()
    return run, company, sector


@pytest.mark.asyncio
async def test_company_thesis_round_trip(db_session: AsyncSession) -> None:
    run, company, sector = await _seed_run_and_entities(db_session)

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
        )
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(CompanyThesis).where(CompanyThesis.run_id == run.id)
        )
    ).scalar_one()
    assert loaded.ticker == "EXMP"
    assert loaded.direction == "overweight"
    assert loaded.judge_status == "not_run"
    assert loaded.judge_reasons is None
    assert loaded.judge_call_id is None
    assert loaded.regeneration_count == 0


@pytest.mark.asyncio
async def test_company_thesis_unique_run_company(db_session: AsyncSession) -> None:
    run, company, sector = await _seed_run_and_entities(db_session)

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
        )
    )
    await db_session.commit()

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
            direction="underweight",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_company_thesis_direction_check(db_session: AsyncSession) -> None:
    run, company, sector = await _seed_run_and_entities(db_session)

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
            direction="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_company_thesis_verifier_status_check(db_session: AsyncSession) -> None:
    run, company, sector = await _seed_run_and_entities(db_session)

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
            verifier_status="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_company_thesis_judge_status_check(db_session: AsyncSession) -> None:
    run, company, sector = await _seed_run_and_entities(db_session)

    db_session.add(
        _make_company_thesis(
            run_id=run.id,
            company_entity_id=company.id,
            sector_entity_id=sector.id,
            judge_status="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
