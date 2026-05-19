import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.services.strategies.funnel_research.core import _run_is_halted


async def _seed_run(session: AsyncSession, *, status: RunStatus) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=status,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


@pytest.mark.asyncio
async def test_run_is_halted_false_when_running(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.running)
    assert await _run_is_halted(session=db_session, run_id=run_id) is False


@pytest.mark.asyncio
async def test_run_is_halted_false_when_queued(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.queued)
    assert await _run_is_halted(session=db_session, run_id=run_id) is False


@pytest.mark.asyncio
async def test_run_is_halted_true_when_paused(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.paused)
    assert await _run_is_halted(session=db_session, run_id=run_id) is True


@pytest.mark.asyncio
async def test_run_is_halted_true_when_failed(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.failed)
    assert await _run_is_halted(session=db_session, run_id=run_id) is True


@pytest.mark.asyncio
async def test_run_is_halted_true_when_cancelled(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.cancelled)
    assert await _run_is_halted(session=db_session, run_id=run_id) is True


@pytest.mark.asyncio
async def test_run_is_halted_true_when_succeeded(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session, status=RunStatus.succeeded)
    assert await _run_is_halted(session=db_session, run_id=run_id) is True
