from app.db import models
from app.db.base import Base

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
