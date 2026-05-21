import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.db.session import session_factory
from app.schemas.budget import TokenUsage
from app.schemas.extraction import EvidenceChunkRef
from app.services.extraction import ExtractionBudgetHaltError, ExtractionError
from app.services.llm.client import LlmCompletionResult
from app.services.strategies.funnel_research.sector.extraction import (
    extract_sector_chunks,
)


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


def _chunk(text: str = "rates rose") -> EvidenceChunkRef:
    return EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text=text,
        attributes={"source": "tiingo_news"},
    )


def _completion(content: str) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="gpt-4o-mini",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        cost_usd=Decimal("0.0001"),
        latency_ms=42,
        log_id=uuid.uuid4(),
    )


async def _pause_noop(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _fail_noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def _ok_llm(_call_index: dict[str, int]) -> Callable[..., Awaitable[LlmCompletionResult]]:
    async def _llm(*_args: Any, **_kwargs: Any) -> LlmCompletionResult:
        _call_index["n"] += 1
        return _completion(
            content='{"candidate_entities": [], "candidate_relations": []}'
        )

    return _llm


async def _seeded_run_id() -> uuid.UUID:
    async with session_factory() as session:
        return await _seed_run(session)


@pytest.mark.asyncio
async def test_extract_sector_chunks_empty_input_returns_empty(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seeded_run_id()
    counter: dict[str, int] = {"n": 0}
    outcome = await extract_sector_chunks(
        session_factory=session_factory,
        run_id=run_id,
        chunks=[],
        llm_complete=_ok_llm(counter),
        orchestrator_pause=_pause_noop,
        orchestrator_fail=_fail_noop,
    )
    assert outcome.results == []
    assert outcome.failures == []
    assert counter["n"] == 0


@pytest.mark.asyncio
async def test_extract_sector_chunks_processes_all_chunks(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seeded_run_id()
    counter: dict[str, int] = {"n": 0}
    chunks = [_chunk(f"chunk-{i}") for i in range(5)]
    outcome = await extract_sector_chunks(
        session_factory=session_factory,
        run_id=run_id,
        chunks=chunks,
        llm_complete=_ok_llm(counter),
        orchestrator_pause=_pause_noop,
        orchestrator_fail=_fail_noop,
    )
    assert len(outcome.results) == 5
    assert outcome.failures == []
    assert counter["n"] == 5


@pytest.mark.asyncio
async def test_extract_sector_chunks_records_failures_as_warn_events(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seeded_run_id()
    chunks = [_chunk("a"), _chunk("b")]

    failure_count = {"n": 0}

    async def flaky_llm(*_args: Any, **_kwargs: Any) -> LlmCompletionResult:
        if failure_count["n"] == 0:
            failure_count["n"] += 1
            raise ExtractionError("simulated extraction error")
        return _completion(
            content='{"candidate_entities": [], "candidate_relations": []}'
        )

    outcome = await extract_sector_chunks(
        session_factory=session_factory,
        run_id=run_id,
        chunks=chunks,
        llm_complete=flaky_llm,
        orchestrator_pause=_pause_noop,
        orchestrator_fail=_fail_noop,
        concurrency=1,
    )

    assert len(outcome.results) + len(outcome.failures) == 2
    assert len(outcome.failures) == 1
    async with session_factory() as session:
        warn_events = (
            await session.execute(
                select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
            )
        ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "sector_extraction_failure"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_extract_sector_chunks_respects_concurrency_cap(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seeded_run_id()
    chunks = [_chunk(f"chunk-{i}") for i in range(6)]
    high_water = {"value": 0, "current": 0}
    gate = asyncio.Event()

    async def slow_llm(*_args: Any, **_kwargs: Any) -> LlmCompletionResult:
        high_water["current"] += 1
        high_water["value"] = max(high_water["value"], high_water["current"])
        if not gate.is_set():
            await asyncio.sleep(0.005)
            gate.set()
        await asyncio.sleep(0.01)
        high_water["current"] -= 1
        return _completion(
            content='{"candidate_entities": [], "candidate_relations": []}'
        )

    outcome = await extract_sector_chunks(
        session_factory=session_factory,
        run_id=run_id,
        chunks=chunks,
        llm_complete=slow_llm,
        orchestrator_pause=_pause_noop,
        orchestrator_fail=_fail_noop,
        concurrency=2,
    )

    assert len(outcome.results) == 6
    assert high_water["value"] <= 2


@pytest.mark.asyncio
async def test_extract_sector_chunks_aborts_on_budget_halt(
    initialized_schema: None,
) -> None:
    """A budget halt on one chunk should abort the fan-out instead of being absorbed."""
    _ = initialized_schema
    run_id = await _seeded_run_id()
    chunks = [_chunk(f"chunk-{i}") for i in range(3)]

    async def halting_llm(*_args: Any, **_kwargs: Any) -> LlmCompletionResult:
        raise ExtractionBudgetHaltError("budget halt")

    with pytest.raises(ExtractionBudgetHaltError):
        await extract_sector_chunks(
            session_factory=session_factory,
            run_id=run_id,
            chunks=chunks,
            llm_complete=halting_llm,
            orchestrator_pause=_pause_noop,
            orchestrator_fail=_fail_noop,
            concurrency=1,
        )


@pytest.mark.asyncio
async def test_extract_sector_chunks_uses_per_task_sessions(
    initialized_schema: None,
) -> None:
    """Each chunk should open its own session via session_factory."""
    _ = initialized_schema
    run_id = await _seeded_run_id()
    chunks = [_chunk(f"chunk-{i}") for i in range(3)]

    factory_call_count = {"n": 0}
    real_factory = session_factory

    def counting_factory() -> AsyncSession:
        factory_call_count["n"] += 1
        return real_factory()

    counter: dict[str, int] = {"n": 0}
    outcome = await extract_sector_chunks(
        session_factory=counting_factory,  # type: ignore[arg-type]
        run_id=run_id,
        chunks=chunks,
        llm_complete=_ok_llm(counter),
        orchestrator_pause=_pause_noop,
        orchestrator_fail=_fail_noop,
        concurrency=2,
    )

    assert len(outcome.results) == 3
    assert factory_call_count["n"] == 3
