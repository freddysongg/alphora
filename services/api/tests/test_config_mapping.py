from datetime import date

import pytest

from app.trading_agents.config_mapping import to_tradingagents_config
from app.trading_agents.types import AnalystKind, LLMProvider, RunConfig


def _make_config(
    *,
    analysts: list[AnalystKind],
    llm_provider: LLMProvider = "openai",
    llm_model: str = "gpt-4o-mini",
    debate_depth: int = 3,
) -> RunConfig:
    return RunConfig(
        ticker="AAPL",
        trade_date=date(2025, 1, 15),
        analysts=analysts,
        llm_provider=llm_provider,
        llm_model=llm_model,
        debate_depth=debate_depth,
    )


def test_to_tradingagents_config_maps_macro_to_market() -> None:
    mapped = to_tradingagents_config(_make_config(analysts=["macro"]))
    assert mapped["selected_analysts"] == ["market"]


def test_to_tradingagents_config_maps_fundamentals_passthrough() -> None:
    mapped = to_tradingagents_config(_make_config(analysts=["fundamentals"]))
    assert mapped["selected_analysts"] == ["fundamentals"]


def test_to_tradingagents_config_maps_sentiment_to_social() -> None:
    mapped = to_tradingagents_config(_make_config(analysts=["sentiment"]))
    assert mapped["selected_analysts"] == ["social"]


def test_to_tradingagents_config_drops_debate_only_roles() -> None:
    mapped = to_tradingagents_config(_make_config(analysts=["bull", "bear", "risk"]))
    assert mapped["selected_analysts"] == []


def test_to_tradingagents_config_full_set_dedupes_and_orders() -> None:
    mapped = to_tradingagents_config(
        _make_config(
            analysts=["bull", "bear", "macro", "fundamentals", "sentiment", "risk"],
        )
    )
    assert mapped["selected_analysts"] == ["market", "fundamentals", "social"]


def test_to_tradingagents_config_preserves_debate_depth() -> None:
    mapped = to_tradingagents_config(_make_config(analysts=["macro"], debate_depth=5))
    assert mapped["debate_rounds"] == 5


def test_to_tradingagents_config_openai_wires_provider() -> None:
    mapped = to_tradingagents_config(
        _make_config(analysts=["macro"], llm_provider="openai", llm_model="gpt-4o")
    )
    inner = mapped["config"]
    assert isinstance(inner, dict)
    assert inner["llm_provider"] == "openai"
    assert inner["deep_think_llm"] == "gpt-4o"
    assert inner["quick_think_llm"] == "gpt-4o"


@pytest.mark.parametrize("provider", ["anthropic", "together"])
def test_to_tradingagents_config_non_openai_leaves_provider_unwired(
    provider: LLMProvider,
) -> None:
    mapped = to_tradingagents_config(
        _make_config(analysts=["macro"], llm_provider=provider, llm_model="claude-3")
    )
    inner = mapped["config"]
    assert isinstance(inner, dict)
    assert "llm_provider" not in inner
    assert inner["deep_think_llm"] == "claude-3"
