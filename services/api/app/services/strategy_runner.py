"""Strategy runner (spec section 6.4) -- Phase 4 implementation.

One async task per (strategy_key, ticker, mode) tuple. Consumes a real-
time bar stream from a broker adapter; evaluates the strategy per bar;
routes signals through risk-caps -> llm_judge -> approval_queue -> broker.
Updates ATR-based trailing stops between bars. Persists every decision
to `strategy_run_events`.

Task 16 lands order submission: when the strategy's target bias differs
from the runner's current sign, the runner builds a `ProposedOrder`,
runs the risk -> judge -> approval -> broker chain, and mirrors the
broker response into `strategy_live_orders`. Trail updates (Task 17)
and EOD flatten (Task 18) extend this in subsequent tasks.

This file is the runner orchestrator only. All pure logic (risk caps,
trail manager, indicator window, judge stub, approval stub) lives in
sibling modules. The runner is the ONLY module that imports both the
broker adapter and the DB session.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pandas as pd  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import Bar, BrokerAdapter, OrderRequest, OrderResponse, Timeframe
from app.db.models_strategy_runner import (
    StrategyLiveOrder,
    StrategyLiveOrderStatus,
    StrategyRiskConfig,
    StrategyRun,
    StrategyRunEventLevel,
    StrategyRunStatus,
)
from app.services.approval_queue import ApprovalRequest, request_approval
from app.services.llm_judge import JudgeLlmClient, JudgeRequest
from app.services.llm_judge import evaluate as judge_evaluate
from app.services.market_clock import RTH_CLOSE_ET_MIN, et_minutes
from app.services.risk_caps import (
    PortfolioSnapshot,
    ProposedOrder,
    RiskCapsProfile,
    check_pre_order,
)
from app.services.strategy_indicator_window import (
    INDICATOR_WINDOW_BARS,
    BoundedBarBuffer,
)
from app.services.strategy_run_events import (
    EVENT_APPROVAL_DECISION,
    EVENT_EOD_FLATTEN,
    EVENT_EVALUATE,
    EVENT_JUDGE_VERDICT,
    EVENT_NOT_TRADABLE,
    EVENT_ORDER_FILL,
    EVENT_ORDER_REJECT,
    EVENT_ORDER_SUBMIT,
    EVENT_POSITION_ADOPTION,
    EVENT_RISK_HALT,
    EVENT_RISK_REJECT,
    EVENT_RISK_THROTTLE,
    EVENT_RUN_STARTED,
    EVENT_RUN_STOPPED,
    EVENT_STOP_HIT,
    emit_strategy_run_event,
)
from app.services.timeframes import resample_bars_to_timeframe
from app.services.trail_manager import TrailMode, TrailState, update_trail
from app.strategies.base import Strategy, StrategyParams, StrategyResult

_DEFAULT_ADOPTION_STOP_FRACTION: Decimal = Decimal("0.05")
_THROTTLE_WINDOW_SECONDS: int = 60
_QUANTITY_QUANTIZE: Decimal = Decimal("0.000001")


@dataclass
class StrategyRunnerContext:
    """Runtime container for one runner.

    `session_maker` is a callable returning a fresh AsyncSession per
    invocation (the runner opens a new session per bar to bound the
    transaction lifetime). `cancel_event` is the runner's only
    cooperative-stop signal -- set it from outside to wind down.
    `current_position` is the runner's authoritative view of the open
    share count (positive = long, negative = short). Task 15 wires
    position adoption to seed this from broker.get_positions().
    """

    run_id: uuid.UUID
    strategy: Strategy
    ticker: str
    mode: Literal["paper", "live"]
    params: StrategyParams
    broker: BrokerAdapter
    session_maker: Callable[[], AsyncSession]
    cancel_event: asyncio.Event
    llm_client: JudgeLlmClient
    indicator_window: BoundedBarBuffer = field(
        default_factory=lambda: BoundedBarBuffer(max_size=INDICATOR_WINDOW_BARS)
    )
    current_position: Decimal = field(default_factory=lambda: Decimal("0"))
    trail_state: TrailState | None = None
    last_exit_bar_ts: datetime | None = None
    orders_in_last_minute: list[datetime] = field(default_factory=list)
    approval_poll_interval_seconds: float = 1.0
    approval_paper_auto_approve_after_seconds: float = 0.0
    approval_live_expires_after_seconds: float = 300.0


async def run(ctx: StrategyRunnerContext) -> None:
    """Main loop. Runs until `ctx.cancel_event` is set or the bar stream
    completes (whichever comes first). Always writes a run_started event
    on entry and a run_stopped event on exit, and updates the
    `strategy_runs` row's status + stopped_at."""
    if ctx.mode == "live":
        from app.config import get_settings

        token = get_settings().human_approval_token.get_secret_value()
        if not token:
            raise RuntimeError(
                "HUMAN_APPROVAL_TOKEN must be set when mode=live; "
                "runner refuses to start without the human-approval contract"
            )
    await _mark_status(ctx, StrategyRunStatus.running, started=True)
    await _emit_event(
        ctx,
        kind=EVENT_RUN_STARTED,
        level=StrategyRunEventLevel.info,
        payload={
            "strategy_key": ctx.strategy.key,
            "ticker": ctx.ticker,
            "mode": ctx.mode,
        },
    )

    final_status: StrategyRunStatus = StrategyRunStatus.stopped
    stop_reason: str = "stream_end"
    stop_level: StrategyRunEventLevel = StrategyRunEventLevel.info
    stop_payload_extra: dict[str, object] = {}
    try:
        try:
            await _adopt_existing_position(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            final_status = StrategyRunStatus.errored
            stop_reason = "adoption_failed"
            stop_level = StrategyRunEventLevel.error
            stop_payload_extra = {"error": str(exc)}
            raise

        iterator = ctx.broker.stream_bars([ctx.ticker], ctx.strategy.primary_timeframe)

        try:
            async for bar in iterator:
                if ctx.cancel_event.is_set():
                    break
                await _process_bar(ctx, bar)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            final_status = StrategyRunStatus.errored
            stop_reason = "bar_processing_failed"
            stop_level = StrategyRunEventLevel.error
            stop_payload_extra = {"error": str(exc)}
            raise
        if ctx.cancel_event.is_set():
            stop_reason = "cancel"
    finally:
        payload: dict[str, object] = {"reason": stop_reason, **stop_payload_extra}
        await _emit_event(
            ctx,
            kind=EVENT_RUN_STOPPED,
            level=stop_level,
            payload=payload,
        )
        await _mark_status(ctx, final_status, stopped=True)


async def _process_bar(ctx: StrategyRunnerContext, bar: Bar) -> None:
    """Append bar, call evaluate, emit evaluate event, and route any bias
    change through the order-submission gate chain.

    Order of operations per bar:
      1. Append + evaluate strategy, emit evaluate event.
      2. Trail-manager exit (if open + spec present) -> close + return.
      3. EOD flatten (requires_rth + last RTH minute + open) -> close + return.
      4. Same-bar re-entry guard against `last_exit_bar_ts` -> suppress.
      5. Bias change -> propose order -> gate chain.
    """
    ctx.indicator_window.append(bar)
    primary = ctx.indicator_window.to_frame()
    secondary_bars: dict[Timeframe, pd.DataFrame] = {
        tf: resample_bars_to_timeframe(primary, tf)
        for tf in ctx.strategy.secondary_timeframes
    }
    result: StrategyResult = ctx.strategy.evaluate(
        primary_bars=primary,
        secondary_bars=secondary_bars,
        current_position=_bias_sign(ctx.current_position),
        params=ctx.params,
    )
    eval_meta: dict[str, float | str] = dict(result.meta)
    if result.stop_pts is not None:
        eval_meta.setdefault("stop_pts", float(result.stop_pts))
    await _emit_event(
        ctx,
        kind=EVENT_EVALUATE,
        level=StrategyRunEventLevel.info,
        payload={
            "target": result.target,
            "stop_pts": result.stop_pts,
            "size_hint": result.size_hint,
            "meta": result.meta,
        },
        bar_ts=bar.as_of,
    )

    if ctx.trail_state is not None and result.trail is not None:
        new_state, exit_signal = update_trail(
            state=ctx.trail_state,
            bar=bar,
            trail_spec=result.trail,
            meta=result.meta,
        )
        ctx.trail_state = new_state
        if exit_signal is not None:
            await _emit_event(
                ctx,
                kind=EVENT_STOP_HIT,
                level=StrategyRunEventLevel.warn,
                payload={
                    "reason": exit_signal.reason,
                    "exit_price": str(exit_signal.exit_price),
                },
                bar_ts=bar.as_of,
            )
            await _submit_close(ctx, bar=bar, strategy_meta=eval_meta)
            return

    if ctx.strategy.requires_rth and ctx.current_position != 0:
        if et_minutes(bar.as_of) == RTH_CLOSE_ET_MIN - 1:
            await _emit_event(
                ctx,
                kind=EVENT_EOD_FLATTEN,
                level=StrategyRunEventLevel.info,
                payload={"position_before": str(ctx.current_position)},
                bar_ts=bar.as_of,
            )
            await _submit_close(ctx, bar=bar, strategy_meta=eval_meta)
            return

    current_sign = _bias_sign(ctx.current_position)
    if result.target == current_sign:
        return

    if (
        current_sign == 0
        and result.target != 0
        and ctx.last_exit_bar_ts is not None
        and bar.as_of == ctx.last_exit_bar_ts
    ):
        await _emit_event(
            ctx,
            kind=EVENT_RISK_THROTTLE,
            level=StrategyRunEventLevel.warn,
            payload={
                "reason": "same_bar_re_entry_guard",
                "exit_bar_ts": ctx.last_exit_bar_ts.isoformat(),
            },
            bar_ts=bar.as_of,
        )
        return

    proposed = _proposed_order(
        ctx=ctx,
        target_bias=result.target,
        latest_close=Decimal(str(bar.close)),
        size_hint=result.size_hint,
    )
    if proposed is None:
        return
    await _submit_via_gates(ctx, bar=bar, proposed=proposed, strategy_meta=eval_meta)


async def _submit_close(
    ctx: StrategyRunnerContext,
    *,
    bar: Bar,
    strategy_meta: dict[str, float | str],
) -> None:
    """Submit a closing order for the current open position via the gate chain."""
    close_qty = abs(ctx.current_position)
    close_side: Literal["buy", "sell"] = (
        "sell" if ctx.current_position > 0 else "buy"
    )
    closing = ProposedOrder(
        ticker=ctx.ticker,
        side=close_side,
        qty=close_qty,
        estimated_fill_price=Decimal(str(bar.close)),
        is_closing=True,
    )
    await _submit_via_gates(ctx, bar=bar, proposed=closing, strategy_meta=strategy_meta)


async def _emit_event(
    ctx: StrategyRunnerContext,
    *,
    kind: str,
    level: StrategyRunEventLevel,
    payload: dict[str, object],
    bar_ts: datetime | None = None,
) -> None:
    async with ctx.session_maker() as session:
        emit_strategy_run_event(
            session,
            run_id=ctx.run_id,
            event_kind=kind,
            level=level,
            payload=payload,
            bar_ts=bar_ts,
        )
        await session.commit()


async def _mark_status(
    ctx: StrategyRunnerContext,
    status: StrategyRunStatus,
    *,
    started: bool = False,
    stopped: bool = False,
) -> None:
    values: dict[str, object] = {"status": status.value}
    if started:
        values["started_at"] = datetime.now(UTC)
    if stopped:
        values["stopped_at"] = datetime.now(UTC)
    async with ctx.session_maker() as session:
        await session.execute(
            update(StrategyRun).where(StrategyRun.id == ctx.run_id).values(**values)
        )
        await session.commit()


async def _load_risk_profile(ctx: StrategyRunnerContext) -> RiskCapsProfile:
    """Fetch the current `strategy_risk_config` row for the runner's mode."""
    async with ctx.session_maker() as session:
        row = await session.scalar(
            select(StrategyRiskConfig).where(StrategyRiskConfig.mode == ctx.mode)
        )
    if row is None:
        raise RuntimeError(
            f"strategy_risk_config row for mode={ctx.mode} not found; "
            "did Alembic 022 seed run?"
        )
    return RiskCapsProfile(
        mode=row.mode,
        max_position_per_ticker_shares=Decimal(str(row.max_position_per_ticker_shares)),
        max_position_per_ticker_notional_usd=Decimal(
            str(row.max_position_per_ticker_notional_usd)
        ),
        max_open_positions=row.max_open_positions,
        max_daily_loss_usd=Decimal(str(row.max_daily_loss_usd)),
        max_consecutive_losses=row.max_consecutive_losses,
        daily_profit_target_usd=Decimal(str(row.daily_profit_target_usd)),
        max_orders_per_minute_per_ticker=row.max_orders_per_minute_per_ticker,
    )


def _bias_sign(current_position: Decimal) -> int:
    if current_position > 0:
        return 1
    if current_position < 0:
        return -1
    return 0


def _portfolio_snapshot(ctx: StrategyRunnerContext) -> PortfolioSnapshot:
    """Build a portfolio snapshot for the risk gate.

    Phase 4 tracks only the runner's own ticker — daily P&L and
    consecutive losses are sourced from the runner's in-memory tally
    (currently zero; richer tracking is Phase 5+). The orders-per-minute
    list is pruned in-place to the last `_THROTTLE_WINDOW_SECONDS`.
    """
    open_positions: dict[str, Decimal] = {}
    if ctx.current_position != 0:
        open_positions[ctx.ticker] = ctx.current_position
    now = datetime.now(UTC)
    threshold = now - timedelta(seconds=_THROTTLE_WINDOW_SECONDS)
    recent = [ts for ts in ctx.orders_in_last_minute if ts > threshold]
    ctx.orders_in_last_minute = recent
    orders_per_ticker = {ctx.ticker: len(recent)}
    return PortfolioSnapshot(
        open_positions_by_ticker=open_positions,
        open_position_count=len(open_positions),
        daily_realized_pnl_usd=Decimal("0"),
        consecutive_losses=0,
        orders_in_last_minute_by_ticker=orders_per_ticker,
    )


def _proposed_order(
    *,
    ctx: StrategyRunnerContext,
    target_bias: int,
    latest_close: Decimal,
    size_hint: int | None,
) -> ProposedOrder | None:
    """Translate (target_bias, size_hint, current_position) into a
    `ProposedOrder` or None if the position already matches the target.

    Phase 4 simplification: only flat->long, flat->short, long->flat,
    short->flat in a single bar. Flip orders (long->short) are routed
    via flat — the closing order goes through this bar, the next bar
    re-evaluates the new bias.
    """
    current_sign = _bias_sign(ctx.current_position)
    if current_sign == target_bias:
        return None
    qty = Decimal(str(size_hint)) if size_hint else Decimal("1")
    is_closing = target_bias == 0
    side: Literal["buy", "sell"]
    if is_closing:
        qty = abs(ctx.current_position)
        side = "sell" if ctx.current_position > 0 else "buy"
    elif target_bias == 1:
        if ctx.current_position < 0:
            qty = abs(ctx.current_position)
            side = "buy"
            is_closing = True
        else:
            side = "buy"
    else:
        if ctx.current_position > 0:
            qty = abs(ctx.current_position)
            side = "sell"
            is_closing = True
        else:
            side = "sell"
    return ProposedOrder(
        ticker=ctx.ticker,
        side=side,
        qty=qty,
        estimated_fill_price=latest_close,
        is_closing=is_closing,
    )


async def _submit_via_gates(
    ctx: StrategyRunnerContext,
    *,
    bar: Bar,
    proposed: ProposedOrder,
    strategy_meta: dict[str, float | str],
) -> None:
    """Tradability -> risk -> judge -> approval -> broker -> mirror.

    Spec §8.3 step 1: tradability is the first gate. Halted symbols
    reject every order (open or close). Non-tradable (e.g. delisted)
    symbols reject every order. A SELL that opens a new short on a
    non-shortable symbol is rejected too; closing trades (buy-to-cover
    or sell-to-close) only need is_tradable + not-halted.

    Emits the full chain of decision events to `strategy_run_events` so
    audit queries can answer "why did/didn't trade X happen". Returns
    early without submitting whenever any gate blocks the order.
    """
    tradability = await ctx.broker.is_tradable(proposed.ticker)
    block_reason: str | None = None
    if tradability.is_halted:
        block_reason = "halted"
    elif not tradability.is_tradable:
        block_reason = "not_tradable"
    elif (
        proposed.side == "sell"
        and not proposed.is_closing
        and not tradability.is_shortable
    ):
        block_reason = "not_shortable"
    if block_reason is not None:
        await _emit_event(
            ctx,
            kind=EVENT_NOT_TRADABLE,
            level=StrategyRunEventLevel.warn,
            payload={
                "ticker": proposed.ticker,
                "side": proposed.side,
                "qty": str(proposed.qty),
                "reason": block_reason,
            },
            bar_ts=bar.as_of,
        )
        return

    profile = await _load_risk_profile(ctx)
    snapshot = _portfolio_snapshot(ctx)
    gate = check_pre_order(profile=profile, portfolio=snapshot, order=proposed)
    if gate.decision != "allow":
        kind = {
            "reject": EVENT_RISK_REJECT,
            "throttle": EVENT_RISK_THROTTLE,
            "halt": EVENT_RISK_HALT,
        }[gate.decision]
        await _emit_event(
            ctx,
            kind=kind,
            level=StrategyRunEventLevel.warn,
            payload={
                "reason": gate.reason,
                "ticker": proposed.ticker,
                "side": proposed.side,
                "qty": str(proposed.qty),
            },
            bar_ts=bar.as_of,
        )
        return

    judge_req = JudgeRequest(
        run_id=ctx.run_id,
        strategy_key=ctx.strategy.key,
        ticker=proposed.ticker,
        side=proposed.side,
        qty=proposed.qty,
        estimated_fill_price=proposed.estimated_fill_price,
        mode=ctx.mode,
        bar_ts=bar.as_of,
        strategy_meta=dict(strategy_meta),
    )
    verdict = await judge_evaluate(
        judge_req,
        session_maker=ctx.session_maker,
        llm_client=ctx.llm_client,
    )
    await _emit_event(
        ctx,
        kind=EVENT_JUDGE_VERDICT,
        level=StrategyRunEventLevel.info,
        payload={
            "decision": verdict.decision,
            "reasoning_md": verdict.reasoning_md,
            "size_multiplier": verdict.size_multiplier,
        },
        bar_ts=bar.as_of,
    )
    if verdict.decision == "veto" and ctx.mode == "live":
        return

    approval_req = ApprovalRequest(
        run_id=ctx.run_id,
        strategy_key=ctx.strategy.key,
        ticker=proposed.ticker,
        side=proposed.side,
        qty=proposed.qty,
        estimated_fill_price=proposed.estimated_fill_price,
        mode=ctx.mode,
        judge_decision=verdict.decision,
        judge_size_multiplier=verdict.size_multiplier,
        judge_verdict_id=verdict.verdict_id,
    )
    decision = await request_approval(
        approval_req,
        session_maker=ctx.session_maker,
        auto_approve_after_seconds=ctx.approval_paper_auto_approve_after_seconds,
        live_expires_after_seconds=ctx.approval_live_expires_after_seconds,
        poll_interval_seconds=ctx.approval_poll_interval_seconds,
    )
    await _emit_event(
        ctx,
        kind=EVENT_APPROVAL_DECISION,
        level=StrategyRunEventLevel.info,
        payload={
            "decision": decision.decision,
            "decided_by": decision.decided_by,
            "decided_at": decision.decided_at.isoformat(),
            "pending_approval_id": str(decision.pending_approval_id),
            "reject_reason": decision.reject_reason,
        },
        bar_ts=bar.as_of,
    )
    if decision.decision != "approved":
        return

    final_qty = proposed.qty
    if (
        not proposed.is_closing
        and verdict.size_multiplier is not None
        and verdict.size_multiplier != 1.0
    ):
        final_qty = (proposed.qty * Decimal(str(verdict.size_multiplier))).quantize(
            _QUANTITY_QUANTIZE
        )
    order_request = OrderRequest(
        ticker=proposed.ticker,
        side=proposed.side,
        quantity=final_qty,
        order_type="market",
        time_in_force="day",
        client_order_id=f"r-{ctx.run_id.hex[:8]}-{int(bar.as_of.timestamp())}",
    )
    live_order_id = uuid.uuid4()
    async with ctx.session_maker() as session:
        session.add(
            StrategyLiveOrder(
                id=live_order_id,
                run_id=ctx.run_id,
                mode=ctx.mode,
                broker_order_id=None,
                client_order_id=order_request.client_order_id,
                ticker=order_request.ticker,
                side=order_request.side,
                qty=order_request.quantity,
                limit_price=None,
                status=StrategyLiveOrderStatus.pending.value,
            )
        )
        await session.commit()
    await _emit_event(
        ctx,
        kind=EVENT_ORDER_SUBMIT,
        level=StrategyRunEventLevel.info,
        payload={
            "live_order_id": str(live_order_id),
            "ticker": order_request.ticker,
            "side": order_request.side,
            "qty": str(order_request.quantity),
        },
        bar_ts=bar.as_of,
    )

    try:
        response: OrderResponse = await ctx.broker.place_order(order_request)
    except Exception as exc:
        async with ctx.session_maker() as session:
            await session.execute(
                update(StrategyLiveOrder)
                .where(StrategyLiveOrder.id == live_order_id)
                .values(
                    status=StrategyLiveOrderStatus.rejected.value,
                    reject_reason=str(exc),
                )
            )
            await session.commit()
        await _emit_event(
            ctx,
            kind=EVENT_ORDER_REJECT,
            level=StrategyRunEventLevel.warn,
            payload={"live_order_id": str(live_order_id), "reason": str(exc)},
            bar_ts=bar.as_of,
        )
        return

    final_status = _map_broker_status(response.status)
    is_filled = final_status == "filled"
    # Optimistic position update: market orders accepted by the broker (status
    # "submitted") are treated as position-changing immediately. This prevents
    # the next bar from seeing a flat position and firing a duplicate entry
    # signal. This is a v1 hack until Phase 6+ stream_order_updates
    # reconciliation lands — at that point the optimistic update should be
    # replaced with reconciliation-driven position tracking.
    is_optimistically_filled = (
        not is_filled
        and final_status == "submitted"
        and order_request.order_type == "market"
    )
    async with ctx.session_maker() as session:
        await session.execute(
            update(StrategyLiveOrder)
            .where(StrategyLiveOrder.id == live_order_id)
            .values(
                broker_order_id=response.broker_order_id,
                status=final_status,
                submitted_at=response.submitted_at,
                filled_at=response.submitted_at if is_filled else None,
                filled_qty=order_request.quantity if is_filled else Decimal("0"),
                avg_fill_price=proposed.estimated_fill_price if is_filled else None,
            )
        )
        await session.commit()

    ctx.orders_in_last_minute.append(datetime.now(UTC))
    if is_filled or is_optimistically_filled:
        delta = (
            order_request.quantity
            if order_request.side == "buy"
            else -order_request.quantity
        )
        ctx.current_position += delta
        if is_filled:
            await _emit_event(
                ctx,
                kind=EVENT_ORDER_FILL,
                level=StrategyRunEventLevel.info,
                payload={
                    "live_order_id": str(live_order_id),
                    "broker_order_id": response.broker_order_id,
                    "filled_qty": str(order_request.quantity),
                    "new_position": str(ctx.current_position),
                },
                bar_ts=bar.as_of,
            )
        # Trail initialization is gated on `is_filled` only, NOT
        # `is_optimistically_filled`. The optimistic path has no confirmed
        # fill price -- seeding TrailState with `proposed.estimated_fill_price`
        # would produce wrong stop levels once the actual fill price diverges.
        # An optimistic-fill position therefore runs without a trail until
        # Phase 6+ `stream_order_updates` reconciliation seeds the trail with
        # the real `avg_fill_price`.
        if is_filled and not proposed.is_closing and ctx.trail_state is None:
            side_trail: Literal["long", "short"] = (
                "long" if order_request.side == "buy" else "short"
            )
            entry_price = proposed.estimated_fill_price
            stop_pts_value: Decimal | None = None
            raw_stop = strategy_meta.get("stop_pts")
            if isinstance(raw_stop, (int, float)):
                stop_pts_value = Decimal(str(raw_stop))
            if stop_pts_value is not None and stop_pts_value > 0:
                initial_stop = (
                    entry_price - stop_pts_value
                    if side_trail == "long"
                    else entry_price + stop_pts_value
                )
            else:
                initial_stop = (
                    entry_price * (Decimal("1") - _DEFAULT_ADOPTION_STOP_FRACTION)
                    if side_trail == "long"
                    else entry_price * (Decimal("1") + _DEFAULT_ADOPTION_STOP_FRACTION)
                )
            ctx.trail_state = TrailState(
                side=side_trail,
                entry_price=entry_price,
                high_watermark=entry_price,
                low_watermark=entry_price,
                current_stop=initial_stop,
                mode=TrailMode.initial,
            )
        if proposed.is_closing:
            ctx.trail_state = None
            ctx.last_exit_bar_ts = bar.as_of


def _map_broker_status(raw: str) -> str:
    """Map BrokerAdapter's OrderStatus to strategy_live_orders.status."""
    if raw == "filled":
        return "filled"
    if raw == "partially_filled":
        return "partially_filled"
    if raw == "canceled":
        return "canceled"
    if raw in ("rejected", "expired"):
        return "rejected"
    return "submitted"


async def _adopt_existing_position(ctx: StrategyRunnerContext) -> None:
    """Query broker for current position on ctx.ticker; seed runner state
    so the first evaluate doesn't re-enter. Writes a `position_adoption`
    event for audit. No-op when flat."""
    positions = await ctx.broker.get_positions()
    matching = [p for p in positions if p.ticker == ctx.ticker and p.quantity != 0]
    if not matching:
        return
    pos = matching[0]
    ctx.current_position = pos.quantity
    side: Literal["long", "short"] = "long" if pos.quantity > 0 else "short"
    entry = pos.avg_entry_price
    stop = (
        entry * (Decimal("1") - _DEFAULT_ADOPTION_STOP_FRACTION)
        if side == "long"
        else entry * (Decimal("1") + _DEFAULT_ADOPTION_STOP_FRACTION)
    )
    ctx.trail_state = TrailState(
        side=side,
        entry_price=entry,
        high_watermark=entry,
        low_watermark=entry,
        current_stop=stop,
        mode=TrailMode.initial,
    )
    await _emit_event(
        ctx,
        kind=EVENT_POSITION_ADOPTION,
        level=StrategyRunEventLevel.info,
        payload={
            "ticker": pos.ticker,
            "quantity": str(pos.quantity),
            "avg_entry_price": str(entry),
            "side": side,
            "initial_stop": str(stop),
        },
    )


__all__ = ["StrategyRunnerContext", "run"]
