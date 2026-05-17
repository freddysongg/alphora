from datetime import date

import pytest
from sqlalchemy import select

from app.db import models
from app.db.base import Base
from app.db.models_runs import FinalRating, ResearchRun, RunStatus
from app.db.session import session_factory

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
