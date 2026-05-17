from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import models
from app.db.base import Base
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import FinalRating, ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.schemas.common import RunStatusEnum, StrategyEnum
from app.schemas.llm import LlmCallStatusEnum

_EXPECTED_TABLES = {
    "research_runs",
    "run_reports",
    "run_events",
    "source_provenance",
    "paper_portfolios",
    "paper_orders",
    "paper_positions",
    "watchlists",
    "watchlist_members",
    "screener_runs",
    "screener_results",
    "provider_checks",
    "application_settings",
    "llm_call_logs",
}


def test_models_module_imports() -> None:
    assert hasattr(models, "ResearchRun")
    assert hasattr(models, "PaperPortfolio")
    assert hasattr(models, "ApplicationSettings")


def test_metadata_contains_all_tables() -> None:
    actual_tables = set(Base.metadata.tables.keys())
    missing = _EXPECTED_TABLES - actual_tables
    assert not missing, f"missing tables: {missing}"


@pytest.mark.usefixtures("initialized_schema")
async def test_final_rating_persists_value_not_member_name() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.succeeded,
            config={},
            final_rating=FinalRating.none_,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        raw = await session.execute(
            select(ResearchRun.__table__.c.final_rating).where(ResearchRun.id == run.id)
        )
        stored = raw.scalar_one()

    assert stored == FinalRating.none_.value
    assert stored == "none"
    assert stored != FinalRating.none_.name


def test_paused_member_in_run_status_enums() -> None:
    assert RunStatus.paused.value == "paused"
    assert RunStatusEnum.paused.value == "paused"
    assert {member.value for member in RunStatus} == {
        member.value for member in RunStatusEnum
    }


def test_strategy_enum_values() -> None:
    assert Strategy.tradingagents.value == "tradingagents"
    assert Strategy.funnel_research.value == "funnel_research"
    assert {member.value for member in Strategy} == {
        member.value for member in StrategyEnum
    }


@pytest.mark.usefixtures("initialized_schema")
async def test_research_run_defaults_strategy_to_tradingagents() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.queued,
            config={},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

    assert run.strategy == Strategy.tradingagents.value


@pytest.mark.usefixtures("initialized_schema")
async def test_research_run_persists_funnel_research_strategy() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.queued,
            config={},
            strategy=Strategy.funnel_research.value,
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert reloaded.strategy == Strategy.funnel_research.value


@pytest.mark.usefixtures("initialized_schema")
async def test_research_run_round_trips_paused_status() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.paused,
            config={},
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert reloaded.status == RunStatus.paused


@pytest.mark.usefixtures("initialized_schema")
async def test_llm_call_log_persists_and_round_trips() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        run_id = run.id

        log = LlmCallLog(
            run_id=run_id,
            model="gpt-4o-mini",
            prompt_hash="a" * 64,
            input_hash="b" * 64,
            input_tokens=120,
            output_tokens=80,
            cached_input_tokens=30,
            reasoning_tokens=10,
            cost_usd=Decimal("0.001234"),
            latency_ms=842,
            status=LlmCallStatus.success,
            error_message=None,
            evidence_ids=["ev_1", "ev_2"],
        )
        session.add(log)
        await session.commit()
        log_id = log.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(LlmCallLog).where(LlmCallLog.id == log_id))
        ).scalar_one()

    assert reloaded.run_id == run_id
    assert reloaded.model == "gpt-4o-mini"
    assert reloaded.prompt_hash == "a" * 64
    assert reloaded.input_hash == "b" * 64
    assert reloaded.input_tokens == 120
    assert reloaded.output_tokens == 80
    assert reloaded.cached_input_tokens == 30
    assert reloaded.reasoning_tokens == 10
    assert reloaded.cost_usd == Decimal("0.001234")
    assert reloaded.latency_ms == 842
    assert reloaded.status == LlmCallStatus.success
    assert reloaded.error_message is None
    assert reloaded.evidence_ids == ["ev_1", "ev_2"]
    assert reloaded.created_at is not None


@pytest.mark.usefixtures("initialized_schema")
async def test_llm_call_log_run_id_set_null_on_run_delete() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        run_id = run.id

        log = LlmCallLog(
            run_id=run_id,
            model="gpt-4o-mini",
            prompt_hash="c" * 64,
            input_hash="d" * 64,
            input_tokens=1,
            output_tokens=1,
            cached_input_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=10,
            status=LlmCallStatus.success,
        )
        session.add(log)
        await session.commit()
        log_id = log.id

        await session.execute(
            ResearchRun.__table__.delete().where(ResearchRun.id == run_id)
        )
        await session.commit()

        stored_run_id = (
            await session.execute(
                select(LlmCallLog.__table__.c.run_id).where(
                    LlmCallLog.__table__.c.id == log_id
                )
            )
        ).scalar_one()
        assert stored_run_id is None


def test_llm_call_status_values() -> None:
    assert LlmCallStatus.success.value == "success"
    assert LlmCallStatus.error.value == "error"
    assert LlmCallStatus.budget_paused.value == "budget_paused"
    assert LlmCallStatus.budget_killed.value == "budget_killed"
    assert {member.value for member in LlmCallStatus} == {
        member.value for member in LlmCallStatusEnum
    }


@pytest.mark.usefixtures("initialized_schema")
async def test_llm_call_log_defaults_apply_when_omitted() -> None:
    async with session_factory() as session:
        log = LlmCallLog(
            model="gpt-5",
            prompt_hash="a" * 64,
            input_hash="b" * 64,
            latency_ms=42,
            status=LlmCallStatus.success,
        )
        session.add(log)
        await session.flush()
        assert log.created_at is not None
        assert log.created_at.tzinfo is not None
        await session.commit()
        await session.refresh(log)
        assert log.input_tokens == 0
        assert log.output_tokens == 0
        assert log.cached_input_tokens == 0
        assert log.reasoning_tokens == 0
        assert log.cost_usd == Decimal("0")
        assert log.created_at is not None
