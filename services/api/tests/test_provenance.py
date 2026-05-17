import threading
from datetime import date

from app.trading_agents.provenance import ProvenanceCollector
from app.trading_agents.types import ProvenanceCall


def _make_call(tool: str = "get_ohlcv") -> ProvenanceCall:
    return ProvenanceCall(
        provider="yfinance",
        tool=tool,
        ticker="AAPL",
        request_at="2025-01-15T12:00:00+00:00",
        latency_ms=120,
        status="success",
        sample_count=42,
        as_of=date(2025, 1, 14),
    )


def test_record_then_drain_returns_calls_in_order() -> None:
    collector = ProvenanceCollector()
    collector.record(_make_call("a"))
    collector.record(_make_call("b"))

    drained = collector.drain()

    assert [c.tool for c in drained] == ["a", "b"]


def test_drain_clears_buffer() -> None:
    collector = ProvenanceCollector()
    collector.record(_make_call())

    collector.drain()

    assert len(collector) == 0
    assert collector.drain() == []


def test_concurrent_record_does_not_lose_items() -> None:
    collector = ProvenanceCollector()
    total_threads = 16
    per_thread = 25

    def producer() -> None:
        for index in range(per_thread):
            collector.record(_make_call(f"tool-{index}"))

    threads = [threading.Thread(target=producer) for _ in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    drained = collector.drain()
    assert len(drained) == total_threads * per_thread
