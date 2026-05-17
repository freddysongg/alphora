from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.models_runs import (
    ResearchRun,
    RunReport,
    RunStatus,
    SourceProvenance,
)
from app.services.run_orchestrator import RunOrchestrator, RunOrchestratorError
from app.trading_agents.adapter import TradingAgentsAdapter


@pytest.fixture()
async def isolated_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


class SuccessFakeGraph:
    def __init__(self, **_: Any) -> None:
        pass

    def propagate(self, _ticker: str, _trade_date: str) -> tuple[object, object]:
        final_state: dict[str, object] = {
            "final_trade_decision": "Final decision: BUY",
            "market_report": "Macro bullish",
            "fundamentals_report": "Strong fundamentals",
            "sentiment_report": "Sentiment positive",
        }
        return final_state, "BUY"


class FailingFakeGraph:
    def __init__(self, **_: Any) -> None:
        pass

    def propagate(self, _ticker: str, _trade_date: str) -> tuple[object, object]:
        raise RuntimeError("upstream provider exploded")


class ProvenanceEmittingAdapter(TradingAgentsAdapter):
    def __init__(self) -> None:
        super().__init__(factory=SuccessFakeGraph)

    def run(self, config: Any) -> Any:
        from app.trading_agents.provenance import ProvenanceCollector
        from app.trading_agents.types import ProvenanceCall, RunResult

        collector = ProvenanceCollector()
        collector.record(
            ProvenanceCall(
                provider="yfinance",
                tool="get_ohlcv",
                ticker=config.ticker,
                request_at="2025-02-01T12:00:00+00:00",
                latency_ms=85,
                status="success",
                sample_count=252,
                as_of=date(2025, 1, 31),
            )
        )
        return RunResult(
            final_rating="buy",
            decision_summary="Final decision: BUY",
            reports=[],
            provenance=collector.drain(),
            wall_clock_ms=42,
        )


async def _insert_queued_run(
    factory: async_sessionmaker[AsyncSession],
    *,
    ticker: str = "AAPL",
    config: dict[str, object] | None = None,
) -> ResearchRun:
    run = ResearchRun(
        id=uuid4(),
        ticker=ticker,
        trade_date=date(2025, 2, 1),
        status=RunStatus.queued,
        config=config
        or {
            "analysts": ["macro", "fundamentals", "sentiment"],
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "debate_depth": 3,
        },
    )
    async with factory() as session:
        session.add(run)
        await session.commit()
    return run


async def test_start_marks_run_running(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.start(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.running
        assert stored.started_at is not None


async def test_execute_marks_succeeded_and_persists_reports(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.execute(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.succeeded
        assert stored.final_rating is not None
        assert stored.final_rating.value == "buy"
        assert stored.final_decision_summary is not None
        assert "BUY" in stored.final_decision_summary
        assert stored.wall_clock_ms is not None
        assert stored.finished_at is not None

        report_rows = (
            await session.execute(select(RunReport).where(RunReport.run_id == run.id))
        ).scalars().all()
        analysts = {report.analyst.value for report in report_rows}
        assert {"macro", "fundamentals", "sentiment"} <= analysts


async def test_execute_persists_provenance_rows(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=ProvenanceEmittingAdapter(),
    )

    await orchestrator.execute(run.id)

    async with isolated_session_factory() as session:
        prov_rows = (
            await session.execute(
                select(SourceProvenance).where(SourceProvenance.run_id == run.id)
            )
        ).scalars().all()
        assert len(prov_rows) == 1
        assert prov_rows[0].provider == "yfinance"
        assert prov_rows[0].tool == "get_ohlcv"
        assert prov_rows[0].sample_count == 252


async def test_execute_failure_marks_failed_with_error(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=FailingFakeGraph),
    )

    await orchestrator.execute(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.failed
        assert stored.error_message == "upstream provider exploded"
        assert stored.finished_at is not None


async def test_cancel_marks_queued_run_cancelled(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.cancel(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.cancelled


async def test_cancel_is_noop_for_terminal_runs(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        stored.status = RunStatus.succeeded
        await session.commit()

    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.cancel(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.succeeded


async def test_missing_run_raises_orchestrator_error(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    with pytest.raises(RunOrchestratorError):
        await orchestrator.start(uuid4())


async def test_execute_skips_cancelled_run(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        stored.status = RunStatus.cancelled
        await session.commit()

    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.execute(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.cancelled
        assert stored.final_rating is None
        assert stored.final_decision_summary is None


async def test_start_skips_already_running_run(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        stored.status = RunStatus.cancelled
        await session.commit()

    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator.start(run.id)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.cancelled


async def test_persist_success_skips_cancelled_run(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.trading_agents.types import RunResult

    run = await _insert_queued_run(isolated_session_factory)
    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        stored.status = RunStatus.cancelled
        await session.commit()

    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )
    fake_result = RunResult(
        final_rating="buy",
        decision_summary="ignored",
        reports=[],
        provenance=[],
        wall_clock_ms=10,
    )

    await orchestrator._persist_success(run.id, fake_result)

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.cancelled
        assert stored.final_rating is None


async def test_mark_failed_skips_cancelled_run(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_queued_run(isolated_session_factory)
    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        stored.status = RunStatus.cancelled
        await session.commit()

    orchestrator = RunOrchestrator(
        session_factory=isolated_session_factory,
        adapter=TradingAgentsAdapter(factory=SuccessFakeGraph),
    )

    await orchestrator._mark_failed(run.id, "should not stick")

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run.id))
        ).scalar_one()
        assert stored.status == RunStatus.cancelled
        assert stored.error_message is None
