import pytest

from app.services.run_orchestrator import (
    RunOrchestratorError,
    resolve_stage_position,
)


def test_tradingagents_running_is_one_of_two() -> None:
    assert resolve_stage_position(strategy="tradingagents", stage_name="running") == (1, 2)


def test_tradingagents_terminal_stages_are_two_of_two() -> None:
    assert resolve_stage_position(strategy="tradingagents", stage_name="succeeded") == (2, 2)
    assert resolve_stage_position(strategy="tradingagents", stage_name="failed") == (2, 2)
    assert resolve_stage_position(strategy="tradingagents", stage_name="cancelled") == (2, 2)


def test_funnel_research_substages_in_order() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="ingest") == (1, 9)
    assert resolve_stage_position(strategy="funnel_research", stage_name="digest") == (2, 9)
    assert resolve_stage_position(strategy="funnel_research", stage_name="synthesize") == (3, 9)
    assert resolve_stage_position(strategy="funnel_research", stage_name="verify") == (4, 9)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="sector_fanout"
    ) == (5, 9)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="company_fanout"
    ) == (6, 9)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="portfolio_brief"
    ) == (7, 9)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="consolidate"
    ) == (8, 9)


def test_funnel_research_terminal_is_nine_of_nine() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="succeeded") == (9, 9)
    assert resolve_stage_position(strategy="funnel_research", stage_name="failed") == (9, 9)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="invented", stage_name="running")


def test_unknown_stage_name_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="tradingagents", stage_name="bogus")
