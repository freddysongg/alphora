import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.macro_brief import ProposedHypothesis


async def _make_run(session: AsyncSession) -> uuid.UUID:
    from datetime import date

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.flush()
    return run.id


@pytest.mark.asyncio
async def test_proposed_hypothesis_writes_hypothesis_row(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    scope_eid = uuid.uuid4()
    proposed = [
        ProposedHypothesis(
            claim_text="Energy outperforms",
            scope_entity_ids=[scope_eid],
            evidence_ids=[uuid.uuid4()],
        )
    ]
    ids = await persist_hypotheses(session=db_session, run_id=run_id, proposed=proposed)
    await db_session.commit()
    assert len(ids) == 1

    row = (await db_session.execute(select(Hypothesis).where(Hypothesis.id == ids[0]))).scalar_one()
    assert row.claim_text == "Energy outperforms"
    assert row.scope_entity_ids == [str(scope_eid)]
    assert row.scope_theme_ids == []
    assert row.status == HypothesisStatus.proposed.value
    assert row.proposed_by_run_id == run_id
    assert row.belief is None


@pytest.mark.asyncio
async def test_empty_proposed_writes_zero_rows(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    ids = await persist_hypotheses(session=db_session, run_id=run_id, proposed=[])
    await db_session.commit()
    assert ids == []
