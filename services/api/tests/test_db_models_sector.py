import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief


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


def _make_sector_entity() -> Entity:
    return Entity(
        id=uuid.uuid4(),
        type=EntityType.sector.value,
        canonical_name="Information Technology",
        aliases=[],
        external_ids={},
        attributes={"gics_code": "45", "gics_level": 1},
    )


@pytest.mark.asyncio
async def test_sector_brief_round_trip(db_session: AsyncSession) -> None:
    run = _make_run()
    sector = _make_sector_entity()
    db_session.add(run)
    db_session.add(sector)
    await db_session.flush()

    brief = SectorBrief(
        run_id=run.id,
        sector_entity_id=sector.id,
        direction="overweight",
        payload={"sector_entity_id": str(sector.id), "themes": [], "companies": []},
        verifier_status="verified",
        regeneration_count=0,
        wall_clock_ms=1234,
    )
    db_session.add(brief)
    await db_session.commit()

    loaded = (
        await db_session.execute(select(SectorBrief).where(SectorBrief.run_id == run.id))
    ).scalar_one()
    assert loaded.direction == "overweight"
    assert loaded.judge_status == "not_run"
    assert loaded.judge_reasons is None
    assert loaded.judge_call_id is None
    assert loaded.regeneration_count == 0


@pytest.mark.asyncio
async def test_sector_brief_unique_run_sector(db_session: AsyncSession) -> None:
    run = _make_run()
    sector = _make_sector_entity()
    db_session.add(run)
    db_session.add(sector)
    await db_session.flush()

    db_session.add(
        SectorBrief(
            run_id=run.id,
            sector_entity_id=sector.id,
            direction="overweight",
            payload={},
            verifier_status="verified",
            regeneration_count=0,
            wall_clock_ms=10,
        )
    )
    await db_session.commit()

    db_session.add(
        SectorBrief(
            run_id=run.id,
            sector_entity_id=sector.id,
            direction="underweight",
            payload={},
            verifier_status="verified",
            regeneration_count=0,
            wall_clock_ms=20,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_sector_brief_direction_check(db_session: AsyncSession) -> None:
    run = _make_run()
    sector = _make_sector_entity()
    db_session.add(run)
    db_session.add(sector)
    await db_session.flush()

    db_session.add(
        SectorBrief(
            run_id=run.id,
            sector_entity_id=sector.id,
            direction="bogus",
            payload={},
            verifier_status="verified",
            regeneration_count=0,
            wall_clock_ms=10,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_sector_brief_judge_status_check(db_session: AsyncSession) -> None:
    run = _make_run()
    sector = _make_sector_entity()
    db_session.add(run)
    db_session.add(sector)
    await db_session.flush()

    db_session.add(
        SectorBrief(
            run_id=run.id,
            sector_entity_id=sector.id,
            direction="overweight",
            payload={},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="bogus_judge",
            wall_clock_ms=10,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_sector_brief_verifier_status_check(db_session: AsyncSession) -> None:
    run = _make_run()
    sector = _make_sector_entity()
    db_session.add(run)
    db_session.add(sector)
    await db_session.flush()

    db_session.add(
        SectorBrief(
            run_id=run.id,
            sector_entity_id=sector.id,
            direction="overweight",
            payload={},
            verifier_status="bogus_verifier",
            regeneration_count=0,
            wall_clock_ms=10,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
