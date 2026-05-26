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
from app.strategies.confluence_long import ConfluenceLongStrategy
from app.strategies.gap_fill import GapFillStrategy
from app.strategies.ict import IctStrategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy
from app.strategies.orb_safe import OrbSafeStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    BbRsiStrategy.key: BbRsiStrategy,
    ConfluenceLongStrategy.key: ConfluenceLongStrategy,
    GapFillStrategy.key: GapFillStrategy,
    IctStrategy.key: IctStrategy,
    MacdRsiAdxStrategy.key: MacdRsiAdxStrategy,
    OrbSafeStrategy.key: OrbSafeStrategy,
}

__all__ = [
    "STRATEGY_REGISTRY",
    "Bars",
    "BbRsiStrategy",
    "ConfluenceLongStrategy",
    "GapFillStrategy",
    "IctStrategy",
    "MacdRsiAdxStrategy",
    "OrbSafeStrategy",
    "Strategy",
    "StrategyParams",
    "StrategyResult",
    "Timeframe",
    "TrailSpec",
]
