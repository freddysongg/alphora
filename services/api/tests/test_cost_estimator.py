"""Tests for the pre-flight run cost estimator."""
from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.schemas.common import StrategyEnum
from app.services.cost_estimator import estimate_run_cost


async def _create_run(strategy: Strategy = Strategy.funnel_research) -> UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker=None,
            trade_date=date(2026, 5, 16),
            strategy=strategy.value,
            status=RunStatus.succeeded,
            config={},
            scope_payload={},
        )
        session.add(run)
        await session.commit()
        return run.id


async def _add_call(
    *,
    run_id: UUID,
    stage: str | None,
    cost: str,
    input_tokens: int = 1000,
    cached_input_tokens: int = 100,
    status: LlmCallStatus = LlmCallStatus.success,
) -> None:
    async with session_factory() as session:
        session.add(
            LlmCallLog(
                run_id=run_id,
                model="gpt-5-mini",
                prompt_hash="x" * 64,
                input_hash="y" * 64,
                input_tokens=input_tokens,
                output_tokens=200,
                cached_input_tokens=cached_input_tokens,
                reasoning_tokens=0,
                cost_usd=Decimal(cost),
                latency_ms=10,
                status=status,
                stage=stage,
                agent_name="synthesis",
                call_index=0,
            )
        )
        await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_when_no_history_returns_zero_per_stage() -> None:
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    assert result.estimated_total_usd == Decimal("0.000000")
    assert result.sample_run_count == 0
    by_stage = {row.stage: row for row in result.stages}
    assert by_stage["macro_synthesis"].sample_size == 0
    assert by_stage["macro_synthesis"].mean_cost_usd == Decimal("0")


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_aggregates_mean_per_stage() -> None:
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.10")
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.30")
    await _add_call(run_id=run_id, stage="sector_synthesis", cost="0.05")
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    by_stage = {row.stage: row for row in result.stages}
    macro = by_stage["macro_synthesis"]
    assert macro.sample_size == 2
    assert macro.mean_cost_usd == Decimal("0.200000")
    sector = by_stage["sector_synthesis"]
    assert sector.sample_size == 1
    assert sector.mean_cost_usd == Decimal("0.050000")
    assert result.estimated_total_usd == Decimal("0.250000")
    assert result.sample_run_count == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_p95_picks_high_percentile_value() -> None:
    run_id = await _create_run()
    for raw in ("0.01", "0.02", "0.03", "0.04", "1.00"):
        await _add_call(run_id=run_id, stage="macro_synthesis", cost=raw)
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    macro = next(row for row in result.stages if row.stage == "macro_synthesis")
    assert macro.p95_cost_usd > Decimal("0.04")
    assert macro.p95_cost_usd <= Decimal("1.00")


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_skips_budget_killed_and_error_rows() -> None:
    run_id = await _create_run()
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="0.10",
        status=LlmCallStatus.success,
    )
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="100.00",
        status=LlmCallStatus.budget_killed,
    )
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="50.00",
        status=LlmCallStatus.error,
    )
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    macro = next(row for row in result.stages if row.stage == "macro_synthesis")
    assert macro.sample_size == 1
    assert macro.mean_cost_usd == Decimal("0.100000")


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_skips_calls_with_no_stage() -> None:
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage=None, cost="100.00")
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    # null-stage rows don't contribute to any stage bucket.
    assert all(row.sample_size == 0 for row in result.stages)
    assert result.estimated_total_usd == Decimal("0.000000")


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_distinct_runs_counted_separately() -> None:
    run_a = await _create_run()
    run_b = await _create_run()
    await _add_call(run_id=run_a, stage="macro_synthesis", cost="0.10")
    await _add_call(run_id=run_b, stage="macro_synthesis", cost="0.30")
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    assert result.sample_run_count == 2


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_strategy_filter_does_not_leak_other_strategies() -> None:
    fr_run = await _create_run(Strategy.funnel_research)
    ta_run = await _create_run(Strategy.tradingagents)
    await _add_call(run_id=fr_run, stage="macro_synthesis", cost="0.10")
    await _add_call(run_id=ta_run, stage="some_other_stage", cost="99.00")
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    by_stage = {row.stage: row for row in result.stages}
    assert by_stage["macro_synthesis"].sample_size == 1
    assert all(
        row.sample_size == 0
        for row in result.stages
        if row.stage != "macro_synthesis"
    )


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_mean_input_tokens_per_stage() -> None:
    run_id = await _create_run()
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="0.10",
        input_tokens=2000,
        cached_input_tokens=500,
    )
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="0.20",
        input_tokens=4000,
        cached_input_tokens=1500,
    )
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    macro = next(row for row in result.stages if row.stage == "macro_synthesis")
    assert macro.mean_input_tokens == cast(float, 3000.0)
    assert macro.mean_cached_input_tokens == cast(float, 1000.0)


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_canonical_stage_order_is_preserved() -> None:
    """The canonical funnel_research stage order should appear first."""
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.05")
    await _add_call(run_id=run_id, stage="judge", cost="0.05")
    await _add_call(run_id=run_id, stage="extraction", cost="0.05")
    async with session_factory() as session:
        result = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    stage_names = [row.stage for row in result.stages]
    assert stage_names.index("macro_synthesis") < stage_names.index("judge")
    assert stage_names.index("judge") < stage_names.index("extraction")


@pytest.mark.usefixtures("initialized_schema")
async def test_estimate_run_cost_includes_belief_update_stage_on_empty_history() -> None:
    async with session_factory() as session:
        estimate = await estimate_run_cost(
            session=session, strategy=StrategyEnum.funnel_research
        )
    stage_names = [row.stage for row in estimate.stages]
    assert "belief_update" in stage_names
    belief_row = next(row for row in estimate.stages if row.stage == "belief_update")
    assert belief_row.sample_size == 0
    assert belief_row.mean_cost_usd == pytest.approx(Decimal("0"))
