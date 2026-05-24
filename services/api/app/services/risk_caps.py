"""Server-side risk-cap enforcement (spec section 8).

Pure-function gate. `check_pre_order(profile, portfolio, order) ->
RiskGateResult` is the only entry point. Evaluation order matches
spec section 8.3: tradability is checked elsewhere (the runner queries
`BrokerAdapter.is_tradable` before calling this gate); here we check
halts (daily loss / consecutive losses / profit target) first, then
position caps, then throttle.

Sell-to-close orders bypass all opening caps -- closing reduces risk
and must never be blocked by gates designed to bound entry.

The runner persists every non-`allow` outcome to `strategy_run_events`
with the reason; this module does not touch the DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

RiskDecision = Literal["allow", "reject", "throttle", "halt"]


@dataclass(frozen=True)
class RiskCapsProfile:
    """Snapshot of the active `strategy_risk_config` row.

    Constructed by the runner at startup (and refreshed periodically).
    Pure data -- does not know the mode select logic.
    """

    mode: str
    max_position_per_ticker_shares: Decimal
    max_position_per_ticker_notional_usd: Decimal
    max_open_positions: int
    max_daily_loss_usd: Decimal
    max_consecutive_losses: int
    daily_profit_target_usd: Decimal
    max_orders_per_minute_per_ticker: int


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Runner's view of the broker's current state.

    `open_positions_by_ticker` is a signed-share-count map (positive =
    long, negative = short). `consecutive_losses` is the count of
    consecutive losing trades on the current run's day.
    """

    open_positions_by_ticker: dict[str, Decimal]
    open_position_count: int
    daily_realized_pnl_usd: Decimal
    consecutive_losses: int
    orders_in_last_minute_by_ticker: dict[str, int]


@dataclass(frozen=True)
class ProposedOrder:
    """An order the runner is about to submit.

    `is_closing=True` short-circuits all opening caps. The runner sets
    this when the proposed order brings absolute position size closer
    to zero (sell-to-close on a long, buy-to-close on a short).
    """

    ticker: str
    side: Literal["buy", "sell"]
    qty: Decimal
    estimated_fill_price: Decimal
    is_closing: bool = False


@dataclass(frozen=True)
class RiskGateResult:
    decision: RiskDecision
    reason: str | None


def check_pre_order(
    *,
    profile: RiskCapsProfile,
    portfolio: PortfolioSnapshot,
    order: ProposedOrder,
) -> RiskGateResult:
    """Apply spec section 8.3 evaluation order.

    Evaluation steps, returning the first non-allow decision:

    1. Sell-to-close bypass: closing orders always allow (they reduce risk).
    2. Halts: daily realized loss cap, consecutive losses cap, daily profit
       target. Halts are evaluated before rejects because once tripped the
       runner stops trading the symbol for the rest of the session, so the
       reason carried back must reflect the halt, not a coincident cap miss.
    3. Position caps: per-ticker share cap and per-ticker notional cap are
       evaluated together so the reason can report every breach (the runner
       and audit queries want the full picture, not just the first rule that
       fired). Then max-open-positions, only counted when the order opens a
       NEW ticker.
    4. Throttle: per-ticker orders-per-minute.

    A non-allow result carries a `reason` string the runner copies into
    `strategy_run_events.payload` so audit queries can answer "why didn't
    trade X happen". The format is `"<rule_name>: <details>"` to keep
    machine-greppable parsing easy.
    """
    if order.is_closing:
        return RiskGateResult(decision="allow", reason=None)

    if portfolio.daily_realized_pnl_usd <= -profile.max_daily_loss_usd:
        return RiskGateResult(
            decision="halt",
            reason=(
                f"max_daily_loss_usd: realized={portfolio.daily_realized_pnl_usd} "
                f"cap=-{profile.max_daily_loss_usd}"
            ),
        )
    if portfolio.consecutive_losses >= profile.max_consecutive_losses:
        return RiskGateResult(
            decision="halt",
            reason=(
                f"max_consecutive_losses: count={portfolio.consecutive_losses} "
                f"cap={profile.max_consecutive_losses}"
            ),
        )
    if portfolio.daily_realized_pnl_usd >= profile.daily_profit_target_usd:
        return RiskGateResult(
            decision="halt",
            reason=(
                f"daily_profit_target_usd: realized={portfolio.daily_realized_pnl_usd} "
                f"target={profile.daily_profit_target_usd}"
            ),
        )

    current_qty = portfolio.open_positions_by_ticker.get(order.ticker, Decimal("0"))
    delta = order.qty if order.side == "buy" else -order.qty
    projected_qty = current_qty + delta
    projected_notional = abs(projected_qty) * order.estimated_fill_price
    breached_position_caps: list[str] = []
    if abs(projected_qty) > profile.max_position_per_ticker_shares:
        breached_position_caps.append(
            f"max_position_per_ticker_shares: projected={projected_qty} "
            f"cap={profile.max_position_per_ticker_shares} ticker={order.ticker}"
        )
    if projected_notional > profile.max_position_per_ticker_notional_usd:
        breached_position_caps.append(
            f"max_position_per_ticker_notional_usd: projected={projected_notional} "
            f"cap={profile.max_position_per_ticker_notional_usd} ticker={order.ticker}"
        )
    if breached_position_caps:
        return RiskGateResult(decision="reject", reason="; ".join(breached_position_caps))
    if order.ticker not in portfolio.open_positions_by_ticker:
        if portfolio.open_position_count >= profile.max_open_positions:
            return RiskGateResult(
                decision="reject",
                reason=(
                    f"max_open_positions: open={portfolio.open_position_count} "
                    f"cap={profile.max_open_positions}"
                ),
            )

    orders_this_minute = portfolio.orders_in_last_minute_by_ticker.get(order.ticker, 0)
    if orders_this_minute >= profile.max_orders_per_minute_per_ticker:
        return RiskGateResult(
            decision="throttle",
            reason=(
                f"max_orders_per_minute_per_ticker: count={orders_this_minute} "
                f"cap={profile.max_orders_per_minute_per_ticker} ticker={order.ticker}"
            ),
        )

    return RiskGateResult(decision="allow", reason=None)


__all__ = [
    "PortfolioSnapshot",
    "ProposedOrder",
    "RiskCapsProfile",
    "RiskDecision",
    "RiskGateResult",
    "check_pre_order",
]
