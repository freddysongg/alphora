from datetime import date

import pytest
from sqlalchemy import select

from app.db import models
from app.db.base import Base
from app.db.models_runs import FinalRating, ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.schemas.common import RunStatusEnum, StrategyEnum

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
