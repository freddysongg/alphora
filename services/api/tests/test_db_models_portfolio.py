import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_portfolio import PortfolioBrief
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


def _make_portfolio_brief(
    *,
    run_id: uuid.UUID,
    verifier_status: str = "verified",
    judge_status: str = "not_run",
) -> PortfolioBrief:
    return PortfolioBrief(
        run_id=run_id,
        payload={"run_id": str(run_id), "sectors": [], "companies": []},
        verifier_status=verifier_status,
        regeneration_count=0,
        judge_status=judge_status,
        wall_clock_ms=12,
    )


async def _seed_run(db_session: AsyncSession) -> ResearchRun:
    run = _make_run()
    db_session.add(run)
    await db_session.flush()
    return run


@pytest.mark.asyncio
async def test_portfolio_brief_round_trip(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)

    db_session.add(_make_portfolio_brief(run_id=run.id))
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(PortfolioBrief).where(PortfolioBrief.run_id == run.id)
        )
    ).scalar_one()
    assert loaded.verifier_status == "verified"
    assert loaded.judge_status == "not_run"
    assert loaded.judge_reasons is None
    assert loaded.judge_call_id is None
    assert loaded.regeneration_count == 0
    assert loaded.wall_clock_ms == 12
    assert loaded.payload["run_id"] == str(run.id)


@pytest.mark.asyncio
async def test_portfolio_brief_unique_run_id(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)

    db_session.add(_make_portfolio_brief(run_id=run.id))
    await db_session.commit()

    db_session.add(_make_portfolio_brief(run_id=run.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_portfolio_brief_verifier_status_check(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)

    db_session.add(_make_portfolio_brief(run_id=run.id, verifier_status="bogus"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_portfolio_brief_judge_status_check(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)

    db_session.add(_make_portfolio_brief(run_id=run.id, judge_status="bogus"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
