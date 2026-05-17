from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Sized
from datetime import UTC, datetime
from types import ModuleType, TracebackType
from typing import Any, Final, Literal

from app.trading_agents.provenance import ProvenanceCollector
from app.trading_agents.types import ProvenanceCall

_INTERFACE_MODULE: Final[str] = "tradingagents.dataflows.interface"

_TOOL_TO_PROVIDER: Final[dict[str, str]] = {
    "get_stock_data": "yfinance",
    "get_stock_indicators": "yfinance",
    "get_fundamentals": "alphavantage",
    "get_financial_statements": "alphavantage",
    "get_insider_transactions": "alphavantage",
    "get_news": "yahoo-news",
    "get_global_news": "yahoo-news",
}


def _tool_label(name: str) -> str:
    """Derive a stable short tool label by stripping the `get_` prefix."""
    return name[len("get_"):] if name.startswith("get_") else name


def _sample_count(result: object) -> int:
    """Best-effort sample count for a vendor call return value.

    Sized values (lists, dicts, dataframes) report `len()`; scalars count as 1.
    Failures (or unsized objects) report 0.
    """
    if isinstance(result, Sized):
        try:
            return len(result)
        except TypeError:
            return 0
    if result is None:
        return 0
    return 1


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class VendorProvenanceHook:
    """Context manager that records provenance for TradingAgents vendor calls.

    On enter, patches known callables on `tradingagents.dataflows.interface` with
    wrappers that emit `ProvenanceCall` records to the supplied collector. On
    exit (including via exception), restores the original callables. If the
    upstream package is not installed, the hook is a no-op.
    """

    def __init__(self, collector: ProvenanceCollector, ticker: str | None) -> None:
        self._collector = collector
        self._ticker = ticker
        self._active = False
        self._module: ModuleType | None = None
        self._originals: dict[str, Callable[..., Any]] = {}

    def __enter__(self) -> VendorProvenanceHook:
        try:
            module = importlib.import_module(_INTERFACE_MODULE)
        except ImportError:
            self._active = False
            return self

        wrapped: dict[str, Callable[..., Any]] = {}
        for tool_name, provider in _TOOL_TO_PROVIDER.items():
            original = getattr(module, tool_name, None)
            if not callable(original):
                continue
            wrapped[tool_name] = original
            setattr(module, tool_name, self._make_wrapper(tool_name, provider, original))

        self._module = module
        self._originals = wrapped
        self._active = bool(wrapped)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if self._active and self._module is not None:
            for tool_name, original in self._originals.items():
                setattr(self._module, tool_name, original)
        self._active = False
        self._originals = {}
        self._module = None
        return False

    def _make_wrapper(
        self,
        tool_name: str,
        provider: str,
        original: Callable[..., Any],
    ) -> Callable[..., Any]:
        collector = self._collector
        ticker = self._ticker
        label = _tool_label(tool_name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            request_at = _utc_now_iso()
            start = time.monotonic()
            try:
                result = original(*args, **kwargs)
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                collector.record(
                    ProvenanceCall(
                        provider=provider,
                        tool=label,
                        ticker=ticker,
                        request_at=request_at,
                        latency_ms=latency_ms,
                        status="failure",
                        sample_count=0,
                        error_message=str(exc),
                    )
                )
                raise
            latency_ms = int((time.monotonic() - start) * 1000)
            collector.record(
                ProvenanceCall(
                    provider=provider,
                    tool=label,
                    ticker=ticker,
                    request_at=request_at,
                    latency_ms=latency_ms,
                    status="success",
                    sample_count=_sample_count(result),
                )
            )
            return result

        return wrapper
