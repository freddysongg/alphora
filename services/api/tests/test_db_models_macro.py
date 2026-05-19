import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_macro import MacroBrief
from app.db.models_runs import ResearchRun, RunStatus, Strategy


@pytest.fixture()
async def db_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_macro_brief_round_trip(db_session: AsyncSession) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.flush()

    brief = MacroBrief(
        run_id=run.id,
        themes=[{"name": "rates", "evidence_ids": [], "confidence": 0.7}],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.6,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
    )
    db_session.add(brief)
    await db_session.commit()

    loaded = (
        await db_session.execute(select(MacroBrief).where(MacroBrief.run_id == run.id))
    ).scalar_one()
    assert loaded.themes[0]["name"] == "rates"
    assert loaded.verifier_status == "verified"


@pytest.mark.asyncio
async def test_macro_brief_run_id_unique(db_session: AsyncSession) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    await db_session.commit()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_macro_brief_verifier_status_check_rejects_invalid(
    db_session: AsyncSession,
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="bogus_status",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
