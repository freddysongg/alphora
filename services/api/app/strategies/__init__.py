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

__all__ = [
    "Bars",
    "Strategy",
    "StrategyParams",
    "StrategyResult",
    "Timeframe",
    "TrailSpec",
]
