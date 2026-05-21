from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import BrokerAdapter


def get_broker_adapter() -> BrokerAdapter:
    """Return the configured broker adapter.

    Currently always Alpaca; multi-broker selection lives here when a
    second adapter (e.g. IBKR) lands.
    """
    return AlpacaAdapter.from_env()
