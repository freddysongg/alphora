"""STRATEGY_REGISTRY tests.

The registry maps `strategy_key` (the class-level `key` attribute) to the
class itself, so a string from env-var config can be resolved to an
instantiable type.
"""
from __future__ import annotations

import pytest

from app.strategies import STRATEGY_REGISTRY
from app.strategies.bb_rsi import BbRsiStrategy
from app.strategies.confluence_long import ConfluenceLongStrategy
from app.strategies.gap_fill import GapFillStrategy
from app.strategies.ict import IctStrategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy
from app.strategies.orb_safe import OrbSafeStrategy


def test_registry_contains_all_six_strategies() -> None:
    assert set(STRATEGY_REGISTRY.keys()) == {
        BbRsiStrategy.key,
        ConfluenceLongStrategy.key,
        GapFillStrategy.key,
        IctStrategy.key,
        MacdRsiAdxStrategy.key,
        OrbSafeStrategy.key,
    }


def test_registry_returns_the_right_class() -> None:
    assert STRATEGY_REGISTRY[MacdRsiAdxStrategy.key] is MacdRsiAdxStrategy
    assert STRATEGY_REGISTRY[BbRsiStrategy.key] is BbRsiStrategy


def test_registry_unknown_key_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        STRATEGY_REGISTRY["definitely_not_a_strategy"]
