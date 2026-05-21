"""Tests for the per-run cost-ledger aggregation."""
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.services.observability import aggregate_cost_ledger


async def _create_run(strategy: Strategy = Strategy.funnel_research) -> UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker=None,
            trade_date=date(2026, 5, 20),
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
    output_tokens: int = 200,
    cached_input_tokens: int = 100,
    status: LlmCallStatus = LlmCallStatus.success,
    model: str = "gpt-5-mini",
) -> None:
    async with session_factory() as session:
        session.add(
            LlmCallLog(
                run_id=run_id,
                model=model,
                prompt_hash="x" * 64,
                input_hash="y" * 64,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
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
async def test_cost_ledger_returns_zero_for_run_with_no_calls() -> None:
    run_id = await _create_run()
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    assert ledger.run_id == run_id
    assert ledger.total_cost_usd == Decimal("0.000000")
    assert ledger.total_calls == 0
    assert ledger.total_input_tokens == 0
    assert ledger.stages == []
    assert ledger.cache_hit_rate == 0.0


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_aggregates_per_stage_cost_and_tokens() -> None:
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.10",
                    input_tokens=400, cached_input_tokens=100)
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.30",
                    input_tokens=600, cached_input_tokens=300)
    await _add_call(run_id=run_id, stage="extraction", cost="0.05",
                    input_tokens=200, cached_input_tokens=0)
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    assert ledger.total_calls == 3
    assert ledger.total_cost_usd == Decimal("0.450000")
    assert ledger.total_input_tokens == 1200
    assert ledger.total_cached_input_tokens == 400
    by_stage = {row.stage: row for row in ledger.stages}
    macro = by_stage["macro_synthesis"]
    extract = by_stage["extraction"]
    assert macro.call_count == 2
    assert macro.total_cost_usd == Decimal("0.400000")
    assert macro.total_input_tokens == 1000
    assert macro.total_cached_input_tokens == 400
    assert macro.cache_hit_rate == 0.4
    assert extract.call_count == 1
    assert extract.total_cost_usd == Decimal("0.050000")


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_skips_non_success_cost_but_counts_call() -> None:
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage="macro_synthesis", cost="0.10")
    await _add_call(
        run_id=run_id,
        stage="macro_synthesis",
        cost="0.99",
        status=LlmCallStatus.budget_killed,
    )
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    assert ledger.total_calls == 2
    assert ledger.total_cost_usd == Decimal("0.100000")
    macro = next(row for row in ledger.stages if row.stage == "macro_synthesis")
    assert macro.call_count == 2
    assert macro.total_cost_usd == Decimal("0.100000")


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_collects_distinct_models_per_stage() -> None:
    run_id = await _create_run()
    await _add_call(
        run_id=run_id, stage="macro_synthesis", cost="0.10", model="gpt-5"
    )
    await _add_call(
        run_id=run_id, stage="macro_synthesis", cost="0.05", model="gpt-5-mini"
    )
    await _add_call(
        run_id=run_id, stage="macro_synthesis", cost="0.05", model="gpt-5"
    )
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    macro = next(row for row in ledger.stages if row.stage == "macro_synthesis")
    assert macro.models == ["gpt-5", "gpt-5-mini"]


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_groups_null_stage_under_unknown() -> None:
    run_id = await _create_run()
    await _add_call(run_id=run_id, stage=None, cost="0.10")
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    assert any(row.stage == "unknown" for row in ledger.stages)


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_does_not_leak_calls_from_other_runs() -> None:
    run_a = await _create_run()
    run_b = await _create_run()
    await _add_call(run_id=run_a, stage="macro_synthesis", cost="0.10")
    await _add_call(run_id=run_b, stage="macro_synthesis", cost="9.99")
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_a)
    assert ledger.total_cost_usd == Decimal("0.100000")
    assert ledger.total_calls == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_cost_ledger_cache_hit_rate_is_zero_when_no_inputs() -> None:
    run_id = await _create_run()
    await _add_call(
        run_id=run_id, stage="macro_synthesis", cost="0.10",
        input_tokens=0, cached_input_tokens=0,
    )
    async with session_factory() as session:
        ledger = await aggregate_cost_ledger(session=session, run_id=run_id)
    assert ledger.cache_hit_rate == 0.0
