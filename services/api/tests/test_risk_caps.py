from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from app.services.risk_caps import (
    PortfolioSnapshot,
    ProposedOrder,
    RiskCapsProfile,
    RiskDecision,
    RiskGateResult,
    check_pre_order,
)


def _paper_profile() -> RiskCapsProfile:
    return RiskCapsProfile(
        mode="paper",
        max_position_per_ticker_shares=Decimal("50"),
        max_position_per_ticker_notional_usd=Decimal("5000"),
        max_open_positions=6,
        max_daily_loss_usd=Decimal("1000"),
        max_consecutive_losses=5,
        daily_profit_target_usd=Decimal("2000"),
        max_orders_per_minute_per_ticker=3,
    )


def _flat_portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        open_positions_by_ticker={},
        open_position_count=0,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )


def _buy(ticker: str = "SPY", qty: str = "1", price: str = "500") -> ProposedOrder:
    return ProposedOrder(
        ticker=ticker,
        side="buy",
        qty=Decimal(qty),
        estimated_fill_price=Decimal(price),
    )


def test_allow_small_buy_on_empty_portfolio() -> None:
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=_flat_portfolio(),
        order=_buy(),
    )
    assert result.decision == "allow"
    assert result.reason is None


def test_reject_when_position_share_cap_breached_by_combined_holding() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={"SPY": Decimal("48")},
        open_position_count=1,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(qty="5"),
    )
    assert result.decision == "reject"
    assert "max_position_per_ticker_shares" in (result.reason or "")


def test_reject_when_position_notional_cap_breached() -> None:
    portfolio = _flat_portfolio()
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(qty="50", price="500"),
    )
    assert result.decision == "reject"
    assert "max_position_per_ticker_notional_usd" in (result.reason or "")


def test_reject_when_max_open_positions_reached() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={
            "A": Decimal("1"), "B": Decimal("1"), "C": Decimal("1"),
            "D": Decimal("1"), "E": Decimal("1"), "F": Decimal("1"),
        },
        open_position_count=6,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(ticker="SPY"),
    )
    assert result.decision == "reject"
    assert "max_open_positions" in (result.reason or "")


def test_allow_adding_to_existing_position_at_max_open_positions() -> None:
    """Adding to a ticker that's already a position must not count as a new
    position -- open_position_count would not increment."""
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={
            "A": Decimal("1"), "B": Decimal("1"), "C": Decimal("1"),
            "D": Decimal("1"), "E": Decimal("1"), "SPY": Decimal("1"),
        },
        open_position_count=6,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(ticker="SPY", qty="1"),
    )
    assert result.decision == "allow"


def test_halt_when_daily_loss_threshold_tripped() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={},
        open_position_count=0,
        daily_realized_pnl_usd=Decimal("-1000"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(),
    )
    assert result.decision == "halt"
    assert "max_daily_loss_usd" in (result.reason or "")


def test_halt_when_consecutive_losses_threshold_tripped() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={},
        open_position_count=0,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=5,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(),
    )
    assert result.decision == "halt"
    assert "max_consecutive_losses" in (result.reason or "")


def test_halt_when_daily_profit_target_reached() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={},
        open_position_count=0,
        daily_realized_pnl_usd=Decimal("2000"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(),
    )
    assert result.decision == "halt"
    assert "daily_profit_target_usd" in (result.reason or "")


def test_throttle_when_orders_per_minute_per_ticker_breached() -> None:
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={},
        open_position_count=0,
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={"SPY": 3},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(ticker="SPY"),
    )
    assert result.decision == "throttle"
    assert "max_orders_per_minute_per_ticker" in (result.reason or "")


def test_evaluation_order_halt_takes_precedence_over_reject() -> None:
    """Per spec section 8.3: daily loss / consecutive loss / profit target ->
    halt is evaluated BEFORE position-cap rejects."""
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={"SPY": Decimal("48")},
        open_position_count=1,
        daily_realized_pnl_usd=Decimal("-1000"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker={},
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=_buy(ticker="SPY", qty="5"),
    )
    assert result.decision == "halt"
    assert "max_daily_loss_usd" in (result.reason or "")


def test_sell_to_close_is_always_allowed_even_at_caps() -> None:
    """Selling to close an existing long is a risk-DECREASING action.
    All caps are designed for opening; closing must not be blocked."""
    portfolio = PortfolioSnapshot(
        open_positions_by_ticker={"SPY": Decimal("50")},
        open_position_count=6,
        daily_realized_pnl_usd=Decimal("-1000"),
        consecutive_losses=5,
        orders_in_last_minute_by_ticker={"SPY": 3},
    )
    sell_to_close = ProposedOrder(
        ticker="SPY",
        side="sell",
        qty=Decimal("50"),
        estimated_fill_price=Decimal("500"),
        is_closing=True,
    )
    result = check_pre_order(
        profile=_paper_profile(),
        portfolio=portfolio,
        order=sell_to_close,
    )
    assert result.decision == "allow"


def test_live_profile_uses_tighter_caps() -> None:
    live = RiskCapsProfile(
        mode="live",
        max_position_per_ticker_shares=Decimal("0.5"),
        max_position_per_ticker_notional_usd=Decimal("25"),
        max_open_positions=2,
        max_daily_loss_usd=Decimal("10"),
        max_consecutive_losses=3,
        daily_profit_target_usd=Decimal("15"),
        max_orders_per_minute_per_ticker=2,
    )
    result = check_pre_order(
        profile=live,
        portfolio=_flat_portfolio(),
        order=_buy(qty="1", price="500"),
    )
    assert result.decision == "reject"
    assert "notional" in (result.reason or "")


@pytest.mark.parametrize("decision", ["allow", "reject", "throttle", "halt"])
def test_risk_gate_result_decision_literal(decision: str) -> None:
    typed_decision = cast(RiskDecision, decision)
    result = RiskGateResult(
        decision=typed_decision,
        reason="t" if decision != "allow" else None,
    )
    assert result.decision == decision
