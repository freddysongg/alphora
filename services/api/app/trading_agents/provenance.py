import threading

from app.trading_agents.types import ProvenanceCall


class ProvenanceCollector:
    """Thread-safe collector for provenance records emitted by adapter tool calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[ProvenanceCall] = []

    def record(self, call: ProvenanceCall) -> None:
        with self._lock:
            self._calls.append(call)

    def drain(self) -> list[ProvenanceCall]:
        with self._lock:
            drained = list(self._calls)
            self._calls.clear()
            return drained

    def __len__(self) -> int:
        with self._lock:
            return len(self._calls)
