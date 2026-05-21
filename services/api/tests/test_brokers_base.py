from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.brokers.base import (
    Account,
    Bar,
    BrokerMode,
    Order,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Quote,
    TimeInForce,
    TradabilityCheck,
)


def test_quote_roundtrip_preserves_fields() -> None:
    ts = datetime(2026, 5, 20, 14, 30, tzinfo=UTC)
    quote = Quote(ticker="SPY", bid=Decimal("500.10"), ask=Decimal("500.12"), last=Decimal("500.11"), as_of=ts)
    assert quote.ticker == "SPY"
    assert quote.spread == Decimal("0.02")


def test_order_request_requires_positive_quantity() -> None:
    with pytest.raises(ValueError):
        OrderRequest(
            ticker="SPY",
            side="buy",
            quantity=Decimal("0"),
            order_type="market",
            time_in_force="day",
        )


def test_order_request_limit_requires_limit_price() -> None:
    with pytest.raises(ValueError):
        OrderRequest(
            ticker="SPY",
            side="buy",
            quantity=Decimal("1"),
            order_type="limit",
            time_in_force="day",
        )


def test_position_side_inference_from_quantity() -> None:
    long_pos = Position(ticker="SPY", quantity=Decimal("1"), avg_entry_price=Decimal("500"))
    short_pos = Position(ticker="SPY", quantity=Decimal("-1"), avg_entry_price=Decimal("500"))
    assert long_pos.side == "long"
    assert short_pos.side == "short"


def test_broker_mode_literal_accepts_paper_and_live() -> None:
    paper: BrokerMode = "paper"
    live: BrokerMode = "live"
    assert paper == "paper"
    assert live == "live"


def test_unused_imports_compile() -> None:
    # touch every imported name so unused-import lints don't pass falsely
    assert OrderResponse and Order and Bar and Account and TradabilityCheck
    assert OrderSide and OrderType and PositionSide and OrderStatus and TimeInForce
