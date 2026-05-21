class BrokerError(Exception):
    """Base class for all broker-layer errors."""


class OrderRejectedError(BrokerError):
    """The broker accepted the request but rejected the order on validation."""

    def __init__(self, message: str, *, broker_order_id: str | None = None) -> None:
        super().__init__(message)
        self.broker_order_id = broker_order_id


class TradabilityError(BrokerError):
    """The ticker is not tradable right now (halted, delisted, unsupported)."""

    def __init__(self, message: str, *, ticker: str) -> None:
        super().__init__(message)
        self.ticker = ticker
