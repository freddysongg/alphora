from typing import Final

from app.trading_agents.types import AnalystKind, RunConfig

_ANALYST_TO_TRADINGAGENTS: Final[dict[AnalystKind, str | None]] = {
    "macro": "market",
    "fundamentals": "fundamentals",
    "sentiment": "social",
    "bull": None,
    "bear": None,
    "risk": None,
}


def _selected_analysts(analysts: list[AnalystKind]) -> list[str]:
    selected: list[str] = []
    for analyst in analysts:
        mapped = _ANALYST_TO_TRADINGAGENTS.get(analyst)
        if mapped is not None and mapped not in selected:
            selected.append(mapped)
    return selected


def to_tradingagents_config(run_config: RunConfig) -> dict[str, object]:
    """Translate Alphora's RunConfig into the kwargs TradingAgentsGraph expects.

    Analyst mapping:
      - macro -> "market"
      - fundamentals -> "fundamentals"
      - sentiment -> "social"
      - bull / bear are debate roles, not selectable analysts
      - risk is handled by TradingAgents' downstream risk manager

    LLM provider is wired into the nested config dict; only "openai" is wired
    explicitly today, other providers are left for future wiring.
    """
    inner_config: dict[str, object] = {
        "deep_think_llm": run_config.llm_model,
        "quick_think_llm": run_config.llm_model,
    }
    if run_config.llm_provider == "openai":
        inner_config["llm_provider"] = "openai"

    return {
        "selected_analysts": _selected_analysts(run_config.analysts),
        "debate_rounds": run_config.debate_depth,
        "config": inner_config,
    }
