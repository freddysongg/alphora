"""Wiring smoke for the belief_update stage in `core._run_funnel`.

The stage's wiring shape is identical to every other funnel stage block —
`_run_is_halted` precedes `_emit_funnel_stage` precedes the runner call. A
true integration test would require setting up `_run_funnel`'s full fixture
surface (fetchers, embedder, http client, chunk-capture mapping); the
selector + runner unit suites already exercise the moving parts. These two
tests cover only the wiring-shape preconditions: the stage scheme registers
belief_update at the right index, and a cancelled run is recognised as
halted by the helper that gates the stage."""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.db.models_runs import (
    ResearchRun,
    RunStatus,
    Strategy,
)
from app.db.session import session_factory


async def _seed_run(status: RunStatus = RunStatus.running) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=status,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    async with session_factory() as session:
        session.add(run)
        await session.commit()
    return run.id


@pytest.mark.asyncio
async def test_stage_scheme_runtime_check_belief_update_at_index_seven(
    initialized_schema: None,
) -> None:
    from app.services.run_orchestrator import STAGE_SCHEMES

    stages = STAGE_SCHEMES["funnel_research"]
    assert stages.index("belief_update") == 7
    assert stages.index("portfolio_brief") == 6
    assert stages.index("consolidate") == 8


@pytest.mark.asyncio
async def test_cancelled_run_is_recognised_as_halted_before_belief_update(
    initialized_schema: None,
) -> None:
    from app.services.strategies.funnel_research import core as core_module

    run_id = await _seed_run(status=RunStatus.cancelled)
    async with session_factory() as session:
        is_halted = await core_module._run_is_halted(session=session, run_id=run_id)
    assert is_halted is True
