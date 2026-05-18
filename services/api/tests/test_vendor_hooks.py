from __future__ import annotations

import sys
from datetime import date
from types import ModuleType
from typing import Any

import pytest

from app.trading_agents.adapter import TradingAgentsAdapter
from app.trading_agents.provenance import ProvenanceCollector
from app.trading_agents.types import RunConfig
from app.trading_agents.vendor_hooks import VendorProvenanceHook

_INTERFACE_PATH = "tradingagents.dataflows.interface"
_PARENT_PATHS = (
    "tradingagents",
    "tradingagents.dataflows",
    _INTERFACE_PATH,
)


def _install_fake_interface(
    monkeypatch: pytest.MonkeyPatch, attrs: dict[str, Any]
) -> ModuleType:
    """Register a synthetic tradingagents package tree exposing `attrs`."""
    tradingagents = ModuleType("tradingagents")
    dataflows = ModuleType("tradingagents.dataflows")
    interface = ModuleType(_INTERFACE_PATH)
    for name, value in attrs.items():
        setattr(interface, name, value)
    monkeypatch.setitem(sys.modules, "tradingagents", tradingagents)
    monkeypatch.setitem(sys.modules, "tradingagents.dataflows", dataflows)
    monkeypatch.setitem(sys.modules, _INTERFACE_PATH, interface)
    return interface


def test_hook_is_noop_when_tradingagents_not_installed() -> None:
    for path in _PARENT_PATHS:
        assert path not in sys.modules, f"unexpected preloaded module: {path}"

    collector = ProvenanceCollector()
    with VendorProvenanceHook(collector, ticker="AAPL") as hook:
        assert hook._active is False
    assert collector.drain() == []


def test_hook_patches_when_module_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_stock_data(ticker: str, _start: str, _end: str) -> list[int]:
        assert ticker == "MSFT"
        return [1, 2, 3, 4, 5, 6, 7]

    interface = _install_fake_interface(monkeypatch, {"get_stock_data": get_stock_data})

    collector = ProvenanceCollector()
    with VendorProvenanceHook(collector, ticker="MSFT"):
        result = interface.get_stock_data("MSFT", "2025-01-01", "2025-01-31")

    assert result == [1, 2, 3, 4, 5, 6, 7]
    calls = collector.drain()
    assert len(calls) == 1
    recorded = calls[0]
    assert recorded.provider == "yfinance"
    assert recorded.tool == "stock_data"
    assert recorded.ticker == "MSFT"
    assert recorded.status == "success"
    assert recorded.sample_count == 7
    assert recorded.error_message is None
    assert recorded.latency_ms >= 0


def test_hook_records_failure_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_news(_ticker: str) -> list[str]:
        raise ValueError("vendor exploded")

    interface = _install_fake_interface(monkeypatch, {"get_news": get_news})

    collector = ProvenanceCollector()
    with VendorProvenanceHook(collector, ticker="AAPL"):
        with pytest.raises(ValueError, match="vendor exploded"):
            interface.get_news("AAPL")

    calls = collector.drain()
    assert len(calls) == 1
    recorded = calls[0]
    assert recorded.status == "failure"
    assert recorded.sample_count == 0
    assert recorded.error_message is not None
    assert "vendor exploded" in recorded.error_message
    assert recorded.provider == "yahoo-news"
    assert recorded.tool == "news"


def test_hook_restores_originals_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_stock_data() -> list[int]:
        return [1, 2]

    def get_fundamentals() -> dict[str, int]:
        return {"pe": 12}

    interface = _install_fake_interface(
        monkeypatch,
        {"get_stock_data": get_stock_data, "get_fundamentals": get_fundamentals},
    )
    original_stock = interface.get_stock_data
    original_fundamentals = interface.get_fundamentals

    collector = ProvenanceCollector()
    with VendorProvenanceHook(collector, ticker="AAPL"):
        assert interface.get_stock_data is not original_stock
        assert interface.get_fundamentals is not original_fundamentals

    assert interface.get_stock_data is original_stock
    assert interface.get_fundamentals is original_fundamentals


def test_hook_restores_originals_on_exception_in_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_stock_data() -> list[int]:
        return [1]

    interface = _install_fake_interface(monkeypatch, {"get_stock_data": get_stock_data})
    original = interface.get_stock_data

    collector = ProvenanceCollector()
    with pytest.raises(RuntimeError, match="boom"):
        with VendorProvenanceHook(collector, ticker="AAPL"):
            assert interface.get_stock_data is not original
            raise RuntimeError("boom")

    assert interface.get_stock_data is original


def test_adapter_invokes_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_stock_data(ticker: str) -> list[int]:
        assert ticker == "AAPL"
        return [1, 2, 3]

    interface = _install_fake_interface(monkeypatch, {"get_stock_data": get_stock_data})

    class FakeGraph:
        def __init__(self, **_: Any) -> None:
            pass

        def propagate(self, ticker: str, _trade_date: str) -> tuple[object, object]:
            interface.get_stock_data(ticker)
            return {"final_trade_decision": "BUY"}, "BUY"

    adapter = TradingAgentsAdapter(factory=FakeGraph)
    config = RunConfig(
        ticker="AAPL",
        trade_date=date(2025, 2, 1),
        analysts=["macro"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        debate_depth=2,
    )

    result = adapter.run(config)

    assert len(result.provenance) == 1
    recorded = result.provenance[0]
    assert recorded.tool == "stock_data"
    assert recorded.provider == "yfinance"
    assert recorded.ticker == "AAPL"
    assert recorded.sample_count == 3
    assert recorded.status == "success"
