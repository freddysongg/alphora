from datetime import date
from typing import Any

import pytest

from app.trading_agents.adapter import TradingAgentsAdapter, _extract_rating
from app.trading_agents.types import RunConfig


class FakeGraph:
    last_kwargs: dict[str, Any] | None = None
    last_propagate: tuple[str, str] | None = None

    def __init__(self, **kwargs: Any) -> None:
        FakeGraph.last_kwargs = kwargs

    def propagate(self, ticker: str, trade_date: str) -> tuple[object, object]:
        FakeGraph.last_propagate = (ticker, trade_date)
        final_state: dict[str, object] = {
            "final_trade_decision": "After review, final decision: BUY at open.",
            "market_report": "Macro looks constructive.",
            "fundamentals_report": "Fundamentals strong.",
            "sentiment_report": "Sentiment improving.",
            "bull_history": "Bull case markdown.",
            "bear_history": "Bear case markdown.",
            "risk_judge_message": "Risk judge sign-off.",
        }
        return final_state, "BUY"


@pytest.fixture(autouse=True)
def _reset_fake_graph() -> None:
    FakeGraph.last_kwargs = None
    FakeGraph.last_propagate = None


def _sample_config() -> RunConfig:
    return RunConfig(
        ticker="MSFT",
        trade_date=date(2025, 2, 1),
        analysts=["macro", "fundamentals", "sentiment", "bull", "bear", "risk"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        debate_depth=3,
    )


def test_adapter_translates_state_into_run_result() -> None:
    adapter = TradingAgentsAdapter(factory=FakeGraph)

    result = adapter.run(_sample_config())

    assert result.final_rating == "buy"
    assert "BUY" in result.decision_summary
    analysts = {report.analyst for report in result.reports}
    assert {"macro", "fundamentals", "sentiment", "bull", "bear", "risk"} <= analysts


def test_adapter_passes_ticker_and_iso_date_to_propagate() -> None:
    adapter = TradingAgentsAdapter(factory=FakeGraph)

    adapter.run(_sample_config())

    assert FakeGraph.last_propagate == ("MSFT", "2025-02-01")


def test_adapter_records_wall_clock_ms_non_negative() -> None:
    adapter = TradingAgentsAdapter(factory=FakeGraph)

    result = adapter.run(_sample_config())

    assert result.wall_clock_ms >= 0


def test_adapter_handles_missing_state_keys_gracefully() -> None:
    class SparseGraph:
        def __init__(self, **_: Any) -> None:
            pass

        def propagate(self, _ticker: str, _trade_date: str) -> tuple[object, object]:
            return {}, "SELL signal confirmed"

    adapter = TradingAgentsAdapter(factory=SparseGraph)

    result = adapter.run(_sample_config())

    assert result.final_rating == "sell"
    assert all(report.markdown == "" for report in result.reports)


def test_adapter_falls_back_to_final_state_decision_text_when_decision_is_empty() -> None:
    class EmptyDecisionGraph:
        def __init__(self, **_: Any) -> None:
            pass

        def propagate(self, _ticker: str, _trade_date: str) -> tuple[object, object]:
            return {"final_trade_decision": "HOLD until earnings."}, ""

    adapter = TradingAgentsAdapter(factory=EmptyDecisionGraph)

    result = adapter.run(_sample_config())

    assert result.final_rating == "hold"
    assert "HOLD" in result.decision_summary


def test_extract_rating_returns_none_when_no_match() -> None:
    assert _extract_rating("inconclusive") == "none"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Final decision: BUY", "buy"),
        ("sell signal", "sell"),
        ("Hold position", "hold"),
        ("recommendation BuY now", "buy"),
    ],
)
def test_extract_rating_is_case_insensitive(text: str, expected: str) -> None:
    assert _extract_rating(text) == expected


def test_adapter_resolves_factory_lazily_when_none_provided() -> None:
    adapter = TradingAgentsAdapter()

    with pytest.raises(ModuleNotFoundError):
        adapter.run(_sample_config())
