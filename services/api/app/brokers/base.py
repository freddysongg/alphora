from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

BrokerMode = Literal["paper", "live"]
OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
TimeInForce = Literal["day", "gtc", "ioc", "fok"]
PositionSide = Literal["long", "short"]
OrderStatus = Literal[
    "pending_new",
    "new",
    "partially_filled",
    "filled",
    "canceled",
    "rejected",
    "expired",
]
OrderStatusFilter = Literal["open", "closed", "all"]
Timeframe = Literal["1min", "5min", "15min", "1h", "1d"]


@dataclass(frozen=True)
class Quote:
    ticker: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    as_of: datetime

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: Decimal
    avg_entry_price: Decimal

    @property
    def side(self) -> PositionSide:
        return "long" if self.quantity >= 0 else "short"


@dataclass(frozen=True)
class Account:
    account_id: str
    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    pattern_day_trader: bool


@dataclass(frozen=True)
class OrderRequest:
    ticker: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"OrderRequest.quantity must be positive, got {self.quantity}")
        if self.order_type in ("limit", "stop_limit") and self.limit_price is None:
            raise ValueError(f"order_type={self.order_type} requires limit_price")
        if self.order_type in ("stop", "stop_limit") and self.stop_price is None:
            raise ValueError(f"order_type={self.order_type} requires stop_price")


@dataclass(frozen=True)
class OrderResponse:
    broker_order_id: str
    client_order_id: str | None
    status: OrderStatus
    submitted_at: datetime


@dataclass(frozen=True)
class Order:
    broker_order_id: str
    client_order_id: str | None
    ticker: str
    side: OrderSide
    quantity: Decimal
    filled_quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    status: OrderStatus
    limit_price: Decimal | None
    stop_price: Decimal | None
    avg_fill_price: Decimal | None
    submitted_at: datetime
    filled_at: datetime | None
    canceled_at: datetime | None


@dataclass(frozen=True)
class TradabilityCheck:
    ticker: str
    is_tradable: bool
    is_shortable: bool
    is_halted: bool
    fractionable: bool
    reason: str | None = None


@dataclass(frozen=True)
class Bar:
    ticker: str
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal | None
    as_of: datetime


class BrokerAdapter(Protocol):
    """Broker-agnostic ordering interface.

    Implementations are constructed via their own `from_env()` classmethod
    or by directly injecting underlying clients (for tests). The `mode`
    attribute reflects which environment this instance is bound to.
    """

    mode: BrokerMode

    async def get_account(self) -> Account: ...
    async def get_quote(self, ticker: str) -> Quote: ...
    async def get_positions(self) -> list[Position]: ...
    async def is_tradable(self, ticker: str) -> TradabilityCheck: ...
    async def place_order(self, order: OrderRequest) -> OrderResponse: ...
    async def cancel_order(self, broker_order_id: str) -> None: ...
    async def list_orders(self, status: OrderStatusFilter = "all") -> list[Order]: ...

    def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]: ...
    def stream_order_updates(self) -> AsyncIterator[Order]: ...
