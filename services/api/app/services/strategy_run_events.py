"""Append-only event log for the strategy runner (spec §11.1).

Writes to `strategy_run_events`. The research pipeline's parallel helper
lives at `app/services/run_events.py` and writes to a separate table
(`run_events`, paired with `research_runs`). Naming is deliberately
distinct — see the Phase 4 plan's §"Critical naming decision".
"""
from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_strategy_runner import StrategyRunEvent, StrategyRunEventLevel

EVENT_RUN_STARTED: Final[str] = "run_started"
EVENT_RUN_STOPPED: Final[str] = "run_stopped"
EVENT_EVALUATE: Final[str] = "evaluate"
EVENT_SIGNAL: Final[str] = "signal"
EVENT_NOT_TRADABLE: Final[str] = "not_tradable"
EVENT_RISK_REJECT: Final[str] = "risk_reject"
EVENT_RISK_THROTTLE: Final[str] = "risk_throttle"
EVENT_RISK_HALT: Final[str] = "risk_halt"
EVENT_JUDGE_VERDICT: Final[str] = "judge_verdict"
EVENT_APPROVAL_DECISION: Final[str] = "approval_decision"
EVENT_ORDER_SUBMIT: Final[str] = "order_submit"
EVENT_ORDER_REJECT: Final[str] = "order_reject"
EVENT_ORDER_FILL: Final[str] = "order_fill"
EVENT_POSITION_ADOPTION: Final[str] = "position_adoption"
EVENT_STOP_HIT: Final[str] = "stop_hit"
EVENT_EOD_FLATTEN: Final[str] = "eod_flatten"
EVENT_UNIVERSE_RESOLVED: Final[str] = "universe_resolved"


def emit_strategy_run_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    event_kind: str,
    level: StrategyRunEventLevel,
    payload: dict[str, object],
    bar_ts: datetime | None = None,
) -> StrategyRunEvent:
    """Add a `StrategyRunEvent` to the session. Caller flushes/commits.

    Returns the event so callers can read attributes if needed (e.g., the
    runner uses the event id when correlating an order with its signal).
    """
    event = StrategyRunEvent(
        run_id=run_id,
        bar_ts=bar_ts,
        event_kind=event_kind,
        level=level.value,
        payload=payload,
    )
    session.add(event)
    return event


__all__ = [
    "EVENT_APPROVAL_DECISION",
    "EVENT_EOD_FLATTEN",
    "EVENT_EVALUATE",
    "EVENT_JUDGE_VERDICT",
    "EVENT_NOT_TRADABLE",
    "EVENT_ORDER_FILL",
    "EVENT_ORDER_REJECT",
    "EVENT_ORDER_SUBMIT",
    "EVENT_POSITION_ADOPTION",
    "EVENT_RISK_HALT",
    "EVENT_RISK_REJECT",
    "EVENT_RISK_THROTTLE",
    "EVENT_RUN_STARTED",
    "EVENT_RUN_STOPPED",
    "EVENT_SIGNAL",
    "EVENT_STOP_HIT",
    "EVENT_UNIVERSE_RESOLVED",
    "emit_strategy_run_event",
]
