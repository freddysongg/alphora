from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

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
    from alpaca.trading.client import TradingClient


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
        raise NotImplementedError

    async def get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError

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
