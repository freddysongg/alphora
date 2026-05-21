from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)

from app.brokers.base import (
    Account,
    Bar,
    BrokerMode,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderStatusFilter,
    Position,
    Quote,
    Timeframe,
    TradabilityCheck,
)
from app.config import get_settings

if TYPE_CHECKING:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.models import Quote as AlpacaQuote
    from alpaca.data.models import Trade as AlpacaTrade
    from alpaca.trading.client import TradingClient
    from alpaca.trading.models import Asset as AlpacaAsset
    from alpaca.trading.models import Order as AlpacaOrder
    from alpaca.trading.models import Position as AlpacaPosition
    from alpaca.trading.models import TradeAccount


_ALPACA_SIDE_BY_OURS: dict[str, AlpacaOrderSide] = {
    "buy": AlpacaOrderSide.BUY,
    "sell": AlpacaOrderSide.SELL,
}

_ALPACA_TIF_BY_OURS: dict[str, AlpacaTimeInForce] = {
    "day": AlpacaTimeInForce.DAY,
    "gtc": AlpacaTimeInForce.GTC,
    "ioc": AlpacaTimeInForce.IOC,
    "fok": AlpacaTimeInForce.FOK,
}


def _build_alpaca_order_request(order: OrderRequest):  # type: ignore[no-untyped-def]
    side = _ALPACA_SIDE_BY_OURS[order.side]
    tif = _ALPACA_TIF_BY_OURS[order.time_in_force]
    common = dict(
        symbol=order.ticker,
        qty=float(order.quantity),
        side=side,
        time_in_force=tif,
        client_order_id=order.client_order_id,
    )
    if order.order_type == "market":
        return MarketOrderRequest(**common)
    if order.order_type == "limit":
        return LimitOrderRequest(**common, limit_price=float(order.limit_price))  # type: ignore[arg-type]
    if order.order_type == "stop":
        return StopOrderRequest(**common, stop_price=float(order.stop_price))  # type: ignore[arg-type]
    if order.order_type == "stop_limit":
        return StopLimitOrderRequest(
            **common,
            limit_price=float(order.limit_price),  # type: ignore[arg-type]
            stop_price=float(order.stop_price),  # type: ignore[arg-type]
        )
    raise ValueError(f"unknown order_type: {order.order_type}")


_STATUS_MAP: dict[str, OrderStatus] = {
    "new": "new",
    "accepted": "new",
    "pending_new": "pending_new",
    "partially_filled": "partially_filled",
    "filled": "filled",
    "canceled": "canceled",
    "cancelled": "canceled",
    "rejected": "rejected",
    "expired": "expired",
}


def _translate_status(raw: str) -> OrderStatus:
    return _STATUS_MAP.get(raw.lower(), "rejected")


def _enum_value(raw: object) -> str:
    """Extract a string value from an alpaca-py enum-or-raw-string field.

    alpaca-py model fields (OrderSide, OrderStatus, TimeInForce, etc.) are
    Pydantic enums whose `str()` yields "EnumName.MEMBER" rather than the
    intended value. Test stubs may pass plain strings. This helper handles
    both: returns `.value` if present, else the value coerced to str.
    """
    value = getattr(raw, "value", raw)
    return str(value)


_FILTER_BY_OURS: dict[OrderStatusFilter, QueryOrderStatus] = {
    "open": QueryOrderStatus.OPEN,
    "closed": QueryOrderStatus.CLOSED,
    "all": QueryOrderStatus.ALL,
}


def _translate_order(raw: object) -> Order:
    def _dec(value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    type_attr = getattr(raw, "order_type", None) or getattr(raw, "type", None)
    return Order(
        broker_order_id=str(getattr(raw, "id")),  # noqa: B009
        client_order_id=str(getattr(raw, "client_order_id")) if getattr(raw, "client_order_id", None) else None,  # noqa: B009
        ticker=str(getattr(raw, "symbol")),  # noqa: B009
        side=_enum_value(getattr(raw, "side")).lower(),  # type: ignore[arg-type]  # noqa: B009
        quantity=Decimal(str(getattr(raw, "qty"))),  # noqa: B009
        filled_quantity=Decimal(str(getattr(raw, "filled_qty", "0"))),
        order_type=_enum_value(type_attr).lower(),  # type: ignore[arg-type]
        time_in_force=_enum_value(getattr(raw, "time_in_force")).lower(),  # type: ignore[arg-type]  # noqa: B009
        status=_translate_status(_enum_value(getattr(raw, "status"))),  # noqa: B009
        limit_price=_dec(getattr(raw, "limit_price", None)),
        stop_price=_dec(getattr(raw, "stop_price", None)),
        avg_fill_price=_dec(getattr(raw, "filled_avg_price", None)),
        submitted_at=getattr(raw, "submitted_at"),  # noqa: B009
        filled_at=getattr(raw, "filled_at", None),
        canceled_at=getattr(raw, "canceled_at", None),
    )


class AlpacaAdapter:
    """BrokerAdapter backed by alpaca-py.

    Construct via `AlpacaAdapter.from_env()` in production; pass mock clients
    directly to the constructor in tests.
    """

    def __init__(
        self,
        trading_client: TradingClient,
        data_client: StockHistoricalDataClient,
        mode: BrokerMode,
    ) -> None:
        self._trading = trading_client
        self._data = data_client
        self.mode: BrokerMode = mode

    @classmethod
    def from_env(cls) -> AlpacaAdapter:
        from alpaca.data.historical.stock import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        settings = get_settings()
        if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
            raise RuntimeError(
                "ALPACA_API_KEY and ALPACA_API_SECRET must be set to construct AlpacaAdapter"
            )
        if settings.alpaca_mode == "live" and not settings.human_approval_token.get_secret_value():
            raise RuntimeError(
                "HUMAN_APPROVAL_TOKEN must be set when ALPACA_MODE=live; "
                "live broker construction is rejected until the env contract is satisfied"
            )
        key = settings.alpaca_api_key.get_secret_value()
        secret = settings.alpaca_api_secret.get_secret_value()
        is_paper = settings.alpaca_mode == "paper"
        trading = TradingClient(api_key=key, secret_key=secret, paper=is_paper)
        data = StockHistoricalDataClient(api_key=key, secret_key=secret)
        return cls(trading_client=trading, data_client=data, mode=settings.alpaca_mode)

    # ---- Phase 0 methods (placeholders, implemented in later tasks) ----

    async def get_account(self) -> Account:
        raw = cast("TradeAccount", await asyncio.to_thread(self._trading.get_account))
        return Account(
            account_id=str(raw.id),
            cash=Decimal(str(raw.cash)),
            equity=Decimal(str(raw.equity)),
            buying_power=Decimal(str(raw.buying_power)),
            pattern_day_trader=bool(raw.pattern_day_trader),
        )

    async def get_quote(self, ticker: str) -> Quote:
        quote_req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
        trade_req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        quote_map, trade_map = await asyncio.gather(
            asyncio.to_thread(self._data.get_stock_latest_quote, quote_req),
            asyncio.to_thread(self._data.get_stock_latest_trade, trade_req),
        )
        raw_quote = cast("AlpacaQuote", quote_map[ticker])
        raw_trade = cast("AlpacaTrade", trade_map[ticker])
        return Quote(
            ticker=ticker,
            bid=Decimal(str(raw_quote.bid_price)),
            ask=Decimal(str(raw_quote.ask_price)),
            last=Decimal(str(raw_trade.price)),
            as_of=raw_quote.timestamp,
        )

    async def get_positions(self) -> list[Position]:
        raw_positions = cast(
            "list[AlpacaPosition]",
            await asyncio.to_thread(self._trading.get_all_positions),
        )
        return [
            Position(
                ticker=str(raw.symbol),
                quantity=Decimal(str(raw.qty)),
                avg_entry_price=Decimal(str(raw.avg_entry_price)),
            )
            for raw in raw_positions
        ]

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        raw = cast("AlpacaAsset", await asyncio.to_thread(self._trading.get_asset, ticker))
        is_tradable = bool(raw.tradable)
        status = str(raw.status)
        reason = None if is_tradable else f"asset status: {status}"
        return TradabilityCheck(
            ticker=ticker,
            is_tradable=is_tradable,
            is_shortable=bool(raw.shortable),
            is_halted=False,  # Alpaca does not expose halt status on the asset endpoint
            fractionable=bool(raw.fractionable),
            reason=reason,
        )

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        alpaca_req = _build_alpaca_order_request(order)
        raw = cast("AlpacaOrder", await asyncio.to_thread(self._trading.submit_order, alpaca_req))
        return OrderResponse(
            broker_order_id=str(raw.id),
            client_order_id=str(raw.client_order_id) if raw.client_order_id else None,
            status=_translate_status(_enum_value(raw.status)),
            submitted_at=raw.submitted_at,
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        await asyncio.to_thread(self._trading.cancel_order_by_id, broker_order_id)

    async def list_orders(self, status: OrderStatusFilter = "all") -> list[Order]:
        req = GetOrdersRequest(status=_FILTER_BY_OURS[status])
        raw_orders = await asyncio.to_thread(self._trading.get_orders, req)
        return [_translate_order(raw) for raw in raw_orders]

    # ---- Streaming methods — deferred to Phase 4 ----

    async def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]:
        raise NotImplementedError("stream_bars is implemented in Phase 4")
        # unreachable, but required to satisfy AsyncIterator return type
        yield

    async def stream_order_updates(self) -> AsyncIterator[Order]:
        raise NotImplementedError("stream_order_updates is implemented in Phase 4")
        yield
