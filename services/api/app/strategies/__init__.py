"""Strategy framework.

Defines the `Strategy` Protocol and supporting dataclasses (spec §6.1).
Concrete strategies live in this package and depend only on
`app.strategies.base`, `app.indicators`, `pandas`, and the stdlib.
They do not touch brokers, DB, or HTTP.
"""

from app.strategies.base import (
    Bars,
    Strategy,
    StrategyParams,
    StrategyResult,
    Timeframe,
    TrailSpec,
)
from app.strategies.bb_rsi import BbRsiStrategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy

__all__ = [
    "Bars",
    "BbRsiStrategy",
    "MacdRsiAdxStrategy",
    "Strategy",
    "StrategyParams",
    "StrategyResult",
    "Timeframe",
    "TrailSpec",
]
