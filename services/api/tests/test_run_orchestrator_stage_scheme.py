import pytest

from app.services.run_orchestrator import (
    RunOrchestratorError,
    resolve_stage_position,
)


def test_funnel_research_substages_in_order() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="ingest") == (1, 10)
    assert resolve_stage_position(strategy="funnel_research", stage_name="digest") == (2, 10)
    assert resolve_stage_position(strategy="funnel_research", stage_name="synthesize") == (3, 10)
    assert resolve_stage_position(strategy="funnel_research", stage_name="verify") == (4, 10)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="sector_fanout"
    ) == (5, 10)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="company_fanout"
    ) == (6, 10)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="portfolio_brief"
    ) == (7, 10)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="belief_update"
    ) == (8, 10)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="consolidate"
    ) == (9, 10)


def test_funnel_research_terminal_is_ten_of_ten() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="succeeded") == (10, 10)
    assert resolve_stage_position(strategy="funnel_research", stage_name="failed") == (10, 10)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="invented", stage_name="running")


def test_unknown_stage_name_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="funnel_research", stage_name="bogus")
