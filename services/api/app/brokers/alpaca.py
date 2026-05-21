from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

from app.brokers.base import (
    Account,
    Bar,
    BrokerMode,
    Order,
    OrderRequest,
    OrderResponse,
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
    from alpaca.trading.models import TradeAccount


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
        raise NotImplementedError

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        raise NotImplementedError

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError

    async def list_orders(self, status: OrderStatusFilter = "all") -> list[Order]:
        raise NotImplementedError

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
