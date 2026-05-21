"""Broker adapter layer.

A single `BrokerAdapter` Protocol defines how the rest of the system talks
to a broker. Phase 0 ships an Alpaca implementation supporting paper and
live endpoints (mode chosen at construction time from env). Streaming
methods (bars, order updates) are deferred to Phase 4.

Nothing outside this package imports the alpaca-py SDK directly. All
broker-specific objects are translated to/from the typed DTOs in
`app.brokers.base` at the adapter boundary.
"""

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import (
    Account,
    Bar,
    BrokerAdapter,
    BrokerMode,
    Order,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderStatusFilter,
    OrderType,
    Position,
    PositionSide,
    Quote,
    Timeframe,
    TimeInForce,
    TradabilityCheck,
)
from app.brokers.errors import (
    BrokerError,
    OrderRejectedError,
    TradabilityError,
)
from app.brokers.factory import get_broker_adapter

__all__ = [
    "Account",
    "AlpacaAdapter",
    "Bar",
    "BrokerAdapter",
    "BrokerError",
    "BrokerMode",
    "Order",
    "OrderRejectedError",
    "OrderRequest",
    "OrderResponse",
    "OrderSide",
    "OrderStatus",
    "OrderStatusFilter",
    "OrderType",
    "Position",
    "PositionSide",
    "Quote",
    "TimeInForce",
    "Timeframe",
    "TradabilityCheck",
    "TradabilityError",
    "get_broker_adapter",
]
