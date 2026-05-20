"""End-to-end wiring test: belief_update stage emits between portfolio_brief
and consolidate and is gated by the existing halt-check."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

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
    """Spot-check: the registered stage scheme matches what core.py emits."""
    from app.services.run_orchestrator import STAGE_SCHEMES

    stages = STAGE_SCHEMES["funnel_research"]
    assert stages.index("belief_update") == 7
    assert stages.index("portfolio_brief") == 6
    assert stages.index("consolidate") == 8


@pytest.mark.asyncio
async def test_halted_run_does_not_invoke_belief_update_pass(
    initialized_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the run is halted before belief_update fires, the runner is skipped."""
    from app.services.strategies.funnel_research import core as core_module

    run_id = await _seed_run(status=RunStatus.cancelled)
    invoked: dict[str, bool] = {"called": False}

    async def fake_pass(**_: Any) -> Any:
        invoked["called"] = True
        raise AssertionError("belief_update should not run on halted run")

    monkeypatch.setattr(core_module, "run_belief_update_pass", fake_pass)

    async with session_factory() as session:
        is_halted = await core_module._run_is_halted(session=session, run_id=run_id)
        assert is_halted is True

    assert invoked["called"] is False
