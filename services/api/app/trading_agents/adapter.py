import importlib
import re
import time
from collections.abc import Callable
from typing import Final, Protocol, cast

from app.trading_agents.config_mapping import to_tradingagents_config
from app.trading_agents.provenance import ProvenanceCollector
from app.trading_agents.types import (
    AnalystKind,
    AnalystReport,
    FinalRating,
    RunConfig,
    RunResult,
)
from app.trading_agents.vendor_hooks import VendorProvenanceHook


class TradingAgentsGraphProtocol(Protocol):
    def propagate(self, ticker: str, trade_date: str) -> tuple[object, object]: ...


GraphFactory = Callable[..., TradingAgentsGraphProtocol]


_REPORT_KEY_BY_ANALYST: Final[dict[AnalystKind, str]] = {
    "macro": "market_report",
    "fundamentals": "fundamentals_report",
    "sentiment": "sentiment_report",
    "bull": "bull_history",
    "bear": "bear_history",
    "risk": "risk_judge_message",
}

_RATING_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(BUY|HOLD|SELL)\b", re.IGNORECASE)


class TradingAgentsAdapter:
    """Adapter around TradingAgentsGraph.

    Resolves the real TradingAgents implementation lazily via importlib so the
    package only needs to be installed where the worker actually runs. Tests
    inject a fake factory.
    """

    def __init__(self, factory: GraphFactory | None = None) -> None:
        self._factory = factory

    def _resolve_factory(self) -> GraphFactory:
        if self._factory is not None:
            return self._factory
        module = importlib.import_module("tradingagents.graph.trading_graph")
        return cast(GraphFactory, module.TradingAgentsGraph)

    def run(self, config: RunConfig) -> RunResult:
        graph_cls = self._resolve_factory()
        ta_config = to_tradingagents_config(config)
        graph = graph_cls(**ta_config)
        collector = ProvenanceCollector()
        start = time.monotonic()
        with VendorProvenanceHook(collector, config.ticker):
            final_state, decision = graph.propagate(config.ticker, config.trade_date.isoformat())
        wall_ms = int((time.monotonic() - start) * 1000)
        return self._build_result(final_state, decision, config, collector, wall_ms)

    def _build_result(
        self,
        final_state: object,
        decision: object,
        config: RunConfig,
        collector: ProvenanceCollector,
        wall_ms: int,
    ) -> RunResult:
        """Translate TradingAgents' propagate output into a RunResult.

        TradingAgents returns a (final_state, decision) tuple. final_state is a
        dict-like mapping with keys such as `final_trade_decision`, `bull_history`,
        `bear_history`, `market_report`, `news_report`, `fundamentals_report`,
        `sentiment_report`, and `risk_judge_message`. Decision is the model's
        terminal text. Missing keys map to empty markdown reports. If the actual
        TradingAgents shape diverges we degrade gracefully rather than raise.
        """
        state_map = _as_mapping(final_state)
        decision_text = _coerce_text(decision) or _coerce_text(
            state_map.get("final_trade_decision")
        )
        reports = _build_reports(state_map, config.analysts)
        rating = _extract_rating(decision_text)
        return RunResult(
            final_rating=rating,
            decision_summary=decision_text,
            reports=reports,
            provenance=collector.drain(),
            wall_clock_ms=wall_ms,
        )


def _as_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _build_reports(
    state_map: dict[str, object], requested: list[AnalystKind]
) -> list[AnalystReport]:
    reports: list[AnalystReport] = []
    for analyst in requested:
        key = _REPORT_KEY_BY_ANALYST.get(analyst)
        if key is None:
            continue
        markdown = _coerce_text(state_map.get(key))
        reports.append(AnalystReport(analyst=analyst, markdown=markdown))
    return reports


def _extract_rating(text: str) -> FinalRating:
    match = _RATING_PATTERN.search(text)
    if match is None:
        return "none"
    token = match.group(1).lower()
    if token == "buy":
        return "buy"
    if token == "sell":
        return "sell"
    if token == "hold":
        return "hold"
    return "none"
