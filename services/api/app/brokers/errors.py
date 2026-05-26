"""Broker-adapter exception hierarchy.

Phase 1 follow-up: the runner needs a stable exception type to catch
when the underlying SDK rejects a request. `BrokerError` is the base;
`BrokerOrderRejected` covers broker-level rejections (insufficient
funds, halt, asset not tradable, malformed request); `BrokerTransientError`
covers network/5xx errors that the caller may retry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.brokers.base import OrderRequest


class BrokerError(Exception):
    """Base for all adapter-level errors."""


class BrokerOrderRejected(BrokerError):  # noqa: N818
    """Broker refused the request. Not retriable without changes."""

    def __init__(self, reason: str, *, request: OrderRequest | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.request = request


class BrokerTransientError(BrokerError):
    """Transient transport-level failure (network, 5xx). Caller may retry."""


__all__ = ["BrokerError", "BrokerOrderRejected", "BrokerTransientError"]
