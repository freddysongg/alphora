"""Bar-by-bar event-driven backtest engine (spec §6.3).

Public surface:
  - SlippageModel, CommissionModel — pessimistic cost defaults.
  - Trade, BacktestResult — engine output dataclasses.
  - simulate(bars, strategy, params, ...) -> BacktestResult — pure-function engine.
  - run_backtest(session, ...) — DB orchestrator: load + simulate + persist.

The engine is pure-function: it takes a pandas DataFrame (OHLCV + UTC
DatetimeIndex) and a `Strategy` Protocol implementation, walks bar-by-bar,
defers fills to the next bar's open (no peeking — spec §6.3 explicit),
and returns a structured result. Persistence is a separate function so
unit tests run without a DB.

Source-bot reference: `/Users/freddy/conductor/workspaces/topStepx/hanoi/
lib/backtest.js` (futures bot). We mirror the bar-by-bar event-driven
shape but NOT: same-bar-close fills, daily caps, EOD flatten,
trail/break-even/take-profit, pressure exit, trend-flip exit. Those
are runner-only concerns (Phase 4+). Backtest is pure signal evaluation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_backtest import (
    BacktestEquityPoint,
    BacktestRun,
    BacktestTrade,
)
from app.services.historical_bars import load_polygon_aggregates_as_dataframe
from app.strategies.base import Strategy, StrategyParams


@dataclass(frozen=True)
class SlippageModel:
    """Per-share-per-side slippage in cents.

    Default -2¢/share per fill per spec §6.3. Applied to each fill so a
    round-trip pays 2*per_share_cents/100 dollars per share against the
    trader. A buy fills above reference; a sell fills below.
    """

    per_share_cents: float = 2.0

    def apply_to_fill(self, *, reference_price: float, side: int) -> float:
        if side == 0:
            return reference_price
        sign = 1 if side > 0 else -1
        return reference_price + sign * (self.per_share_cents / 100.0)


@dataclass(frozen=True)
class CommissionModel:
    """Per-fill commission in USD.

    Default $0 per spec §6.3. Both an entry fill and an exit fill each
    pay one `per_trade_usd` cost (a round-trip trade pays
    2 * per_trade_usd in commissions).
    """

    per_trade_usd: float = 0.0

    def cost_per_fill(self) -> float:
        return self.per_trade_usd


TradeExitReason = Literal["signal", "final-bar"]


@dataclass(frozen=True)
class Trade:
    """One completed round-trip trade.

    `side` is +1 (long) or -1 (short). `shares` is a positive count.
    `pnl_usd` = (exit_price - entry_price) * side * shares  - 2 * commission.
    """

    side: int
    entry_bar_index: int
    exit_bar_index: int
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl_usd: float
    bars_held: int
    exit_reason: TradeExitReason


@dataclass(frozen=True)
class BacktestResult:
    """Engine output (spec §6.3).

    `equity_per_bar` is cumulative realized + open-trade-mark P&L in USD
    after each bar, aligned 1:1 with the input `bars` index. The
    persistence step samples this into a daily series for the
    `backtest_equity` table.
    """

    bar_count: int
    trades: list[Trade]
    equity_per_bar: list[float]
    max_drawdown_usd: float
    net_pnl_usd: float
    win_count: int
    loss_count: int
    profit_factor: float | None


def simulate(
    *,
    bars: pd.DataFrame,
    strategy: Strategy,
    params: StrategyParams,
    slippage: SlippageModel | None = None,
    commission: CommissionModel | None = None,
    position_size_shares: int = 1,
) -> BacktestResult:
    """Bar-by-bar event-driven simulator (spec §6.3).

    For each bar `i`:
      1. Call `strategy.evaluate(bars_view, {}, current_position_shares, params)`
         where `bars_view = bars.iloc[: i + 1]`.
      2. If the strategy's `target` (in {-1, 0, +1}) differs from the
         current bias, defer the fill to bar `i+1`'s open ± slippage. If
         `i` is the last bar, no entry (no peeking). The next bar's open
         becomes a real exit/entry on iteration `i+1`.
      3. At the end of the series, force-close any open position at the
         last bar's close ± slippage (mirrors source bot's tail-handling).

    Returns a `BacktestResult` with the trade log, per-bar equity, and
    summary stats. The engine is pure — no DB, no broker, no logging side
    effects.
    """
    if slippage is None:
        slippage = SlippageModel()
    if commission is None:
        commission = CommissionModel()
    bar_count = len(bars)
    if bar_count == 0:
        return BacktestResult(
            bar_count=0,
            trades=[],
            equity_per_bar=[],
            max_drawdown_usd=0.0,
            net_pnl_usd=0.0,
            win_count=0,
            loss_count=0,
            profit_factor=None,
        )

    open_positions: list[Trade] = []  # singleton list — at most one open trade at a time
    trades: list[Trade] = []
    pending_target: int | None = None  # bias requested at the previous bar
    equity_per_bar: list[float] = []
    realized_pnl: float = 0.0

    timestamps = bars.index
    opens = bars["open"].astype(float).to_numpy()
    closes = bars["close"].astype(float).to_numpy()

    def _position_bias() -> int:
        if not open_positions:
            return 0
        return open_positions[0].side

    def _open_trade(bar_index: int, side: int) -> None:
        ref_open = float(opens[bar_index])
        fill = slippage.apply_to_fill(reference_price=ref_open, side=side)
        ts = timestamps[bar_index]
        trade = Trade(
            side=side,
            entry_bar_index=bar_index,
            exit_bar_index=bar_index,  # placeholder; updated on close
            entry_ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            exit_ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            entry_price=fill,
            exit_price=fill,
            shares=position_size_shares,
            pnl_usd=-commission.cost_per_fill(),
            bars_held=0,
            exit_reason="signal",
        )
        open_positions.append(trade)

    def _close_trade(bar_index: int, reason: TradeExitReason) -> Trade:
        nonlocal realized_pnl
        existing = open_positions.pop()
        ref_open = float(opens[bar_index]) if reason == "signal" else float(closes[bar_index])
        # On a signal close, the close-side is opposite the entry side.
        fill = slippage.apply_to_fill(reference_price=ref_open, side=-existing.side)
        ts = timestamps[bar_index]
        gross_pnl = (fill - existing.entry_price) * existing.side * existing.shares
        # The opening fill already charged one commission (stored as
        # negative pnl_usd on the open trade); charge one more here.
        net_pnl = existing.pnl_usd + gross_pnl - commission.cost_per_fill()
        closed = Trade(
            side=existing.side,
            entry_bar_index=existing.entry_bar_index,
            exit_bar_index=bar_index,
            entry_ts=existing.entry_ts,
            exit_ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            entry_price=existing.entry_price,
            exit_price=fill,
            shares=existing.shares,
            pnl_usd=net_pnl,
            bars_held=bar_index - existing.entry_bar_index,
            exit_reason=reason,
        )
        realized_pnl += net_pnl
        return closed

    for i in range(bar_count):
        # 1. Materialize any pending target from the previous bar.
        if pending_target is not None and i < bar_count:
            current_bias = _position_bias()
            if pending_target != current_bias:
                if current_bias != 0:
                    trades.append(_close_trade(bar_index=i, reason="signal"))
                if pending_target != 0:
                    _open_trade(bar_index=i, side=pending_target)
            pending_target = None

        # 2. Ask the strategy for its target on the just-closed bar.
        bars_view = bars.iloc[: i + 1]
        current_position_shares = (
            open_positions[0].side * open_positions[0].shares if open_positions else 0
        )
        result = strategy.evaluate(
            primary_bars=bars_view,
            secondary_bars={},
            current_position=current_position_shares,
            params=params,
        )
        target = int(result.target)

        # 3. Defer to next bar's open if the target differs from current bias.
        if i < bar_count - 1:
            if target != _position_bias():
                pending_target = target
            else:
                pending_target = None
        else:
            pending_target = None  # last bar: no entry possible

        # 4. Record per-bar equity (realized + open-trade mark-to-market).
        open_mark = 0.0
        if open_positions:
            ot = open_positions[0]
            open_mark = (float(closes[i]) - ot.entry_price) * ot.side * ot.shares
        equity_per_bar.append(realized_pnl + open_mark)

    # 5. Final-bar force-close: any still-open position closes at the last
    # bar's close ± slippage (matches source bot's tail logic). After this
    # the equity_per_bar's last entry equals realized_pnl (no more open
    # mark) but we recompute the final entry to avoid double-counting:
    # the position's open-mark was already added to equity_per_bar[-1].
    if open_positions:
        last_index = bar_count - 1
        forced = _close_trade(bar_index=last_index, reason="final-bar")
        trades.append(forced)
        equity_per_bar[-1] = realized_pnl

    # 6. Summary stats.
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd < 0]
    gross_win = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    profit_factor: float | None = None
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")
    peak = 0.0
    max_dd = 0.0
    for eq in equity_per_bar:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    net_pnl = equity_per_bar[-1] if equity_per_bar else 0.0
    return BacktestResult(
        bar_count=bar_count,
        trades=trades,
        equity_per_bar=equity_per_bar,
        max_drawdown_usd=max_dd,
        net_pnl_usd=net_pnl,
        win_count=len(wins),
        loss_count=len(losses),
        profit_factor=profit_factor,
    )


async def persist_backtest_result(
    session: AsyncSession,
    *,
    result: BacktestResult,
    bars: pd.DataFrame,
    strategy_key: str,
    ticker: str,
    timeframe: str,
    params: StrategyParams,
    slippage: SlippageModel,
    commission: CommissionModel,
    position_size_shares: int,
) -> uuid.UUID:
    """Persist a `BacktestResult` to the three Phase 2 tables.

    Equity is grouped by UTC day (one row per day, recording end-of-day
    equity and the running drawdown at that point). Returns the new
    `backtests.id`.
    """
    if result.bar_count == 0:
        raise ValueError("cannot persist a backtest result with zero bars")
    run_id = uuid.uuid4()
    from_ts_obj = bars.index[0]
    to_ts_obj = bars.index[-1]
    from_ts = from_ts_obj.to_pydatetime() if hasattr(from_ts_obj, "to_pydatetime") else from_ts_obj
    to_ts = to_ts_obj.to_pydatetime() if hasattr(to_ts_obj, "to_pydatetime") else to_ts_obj
    run = BacktestRun(
        id=run_id,
        strategy_key=strategy_key,
        ticker=ticker,
        timeframe=timeframe,
        from_ts=from_ts,
        to_ts=to_ts,
        params=dict(params),
        slippage_per_share_cents=slippage.per_share_cents,
        commission_per_trade_usd=commission.per_trade_usd,
        position_size_shares=position_size_shares,
        bar_count=result.bar_count,
        trade_count=len(result.trades),
        net_pnl_usd=result.net_pnl_usd,
        win_count=result.win_count,
        loss_count=result.loss_count,
        max_drawdown_usd=result.max_drawdown_usd,
        profit_factor=(
            None
            if result.profit_factor is None or result.profit_factor == float("inf")
            else result.profit_factor
        ),
    )
    session.add(run)
    # Flush so the FK target row exists before children are inserted —
    # SQLAlchemy's unit of work can't always topologically order
    # parent-before-child when the child references the parent by
    # foreign-key value rather than via a `relationship()` link.
    await session.flush()
    for t in result.trades:
        session.add(
            BacktestTrade(
                backtest_id=run_id,
                side=t.side,
                entry_bar_index=t.entry_bar_index,
                exit_bar_index=t.exit_bar_index,
                entry_ts=t.entry_ts,
                exit_ts=t.exit_ts,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                shares=t.shares,
                pnl_usd=t.pnl_usd,
                bars_held=t.bars_held,
                exit_reason=t.exit_reason,
            )
        )

    daily_last_equity: dict[date, float] = {}
    for ts, eq in zip(bars.index, result.equity_per_bar, strict=True):
        day_key: date = ts.date() if hasattr(ts, "date") else ts
        daily_last_equity[day_key] = eq
    peak = 0.0
    for day in sorted(daily_last_equity.keys()):
        eq = daily_last_equity[day]
        if eq > peak:
            peak = eq
        dd = peak - eq
        session.add(
            BacktestEquityPoint(
                backtest_id=run_id,
                day=day,
                equity_usd=eq,
                drawdown_usd=dd,
            )
        )

    await session.commit()
    return run_id


async def run_backtest(
    session: AsyncSession,
    *,
    strategy: Strategy,
    ticker: str,
    from_ts: datetime,
    to_ts: datetime,
    params: StrategyParams,
    slippage: SlippageModel | None = None,
    commission: CommissionModel | None = None,
    position_size_shares: int = 1,
    timeframe: str = "1min",
) -> uuid.UUID:
    """End-to-end orchestrator: load OHLCV -> simulate -> persist.

    Raises `ValueError` if the loader returns no bars for the range.
    """
    if slippage is None:
        slippage = SlippageModel()
    if commission is None:
        commission = CommissionModel()
    bars = await load_polygon_aggregates_as_dataframe(
        session, ticker=ticker, from_ts=from_ts, to_ts=to_ts
    )
    if bars.empty:
        raise ValueError(
            f"no bars for ticker={ticker} between {from_ts.isoformat()} "
            f"and {to_ts.isoformat()}"
        )
    result = simulate(
        bars=bars,
        strategy=strategy,
        params=params,
        slippage=slippage,
        commission=commission,
        position_size_shares=position_size_shares,
    )
    return await persist_backtest_result(
        session,
        result=result,
        bars=bars,
        strategy_key=strategy.key,
        ticker=ticker,
        timeframe=timeframe,
        params=params,
        slippage=slippage,
        commission=commission,
        position_size_shares=position_size_shares,
    )


__all__ = [
    "BacktestResult",
    "CommissionModel",
    "SlippageModel",
    "Trade",
    "TradeExitReason",
    "persist_backtest_result",
    "run_backtest",
    "simulate",
]
