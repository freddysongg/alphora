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
    assert resolve_stage_position(strategy="funnel_research", stage_name="ingest") == (1, 7)
    assert resolve_stage_position(strategy="funnel_research", stage_name="digest") == (2, 7)
    assert resolve_stage_position(strategy="funnel_research", stage_name="synthesize") == (3, 7)
    assert resolve_stage_position(strategy="funnel_research", stage_name="verify") == (4, 7)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="sector_fanout"
    ) == (5, 7)
    assert resolve_stage_position(
        strategy="funnel_research", stage_name="consolidate"
    ) == (6, 7)


def test_funnel_research_terminal_is_seven_of_seven() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="succeeded") == (7, 7)
    assert resolve_stage_position(strategy="funnel_research", stage_name="failed") == (7, 7)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="invented", stage_name="running")


def test_unknown_stage_name_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="tradingagents", stage_name="bogus")
