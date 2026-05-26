"""Approval queue (spec sections 4.5, 4.6, and 9).

Phase 4 ships the paper auto-approve branch as a stub. Phase 7 adds:
- `pending_approvals` DB table
- the `--human-token`-gated approve endpoint
- the web UI surface

The runner calls `request_approval(...)` after the judge has weighed in;
paper mode auto-approves immediately (decided_by="auto"), live mode
waits for `pending_approvals.status == "approved"` (Phase 7).

ApprovalRequest / ApprovalDecision wire shapes are the persistence
target — keep stable through Phase 7.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.services.llm_judge import JudgeDecision

ApprovalStatus = Literal["approved", "rejected", "expired"]


@dataclass(frozen=True)
class ApprovalRequest:
    """Input to the queue. The runner passes one of these per order."""

    strategy_key: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: Decimal
    estimated_fill_price: Decimal
    mode: Literal["paper", "live"]
    judge_decision: JudgeDecision
    judge_size_multiplier: float | None


@dataclass(frozen=True)
class ApprovalDecision:
    """Outcome. `decided_by` is "auto" for paper, "human:<user_id>" for
    live (Phase 7). `decided_at` is when the decision was recorded."""

    decision: ApprovalStatus
    decided_by: str
    decided_at: datetime


async def request_approval(request: ApprovalRequest) -> ApprovalDecision:
    """Phase 4: paper auto-approves; live raises NotImplementedError.

    Live behavior arrives in Phase 7. The runner's caller catches
    NotImplementedError and surfaces "live mode not yet supported" — it
    must not try to submit live orders before Phase 7 lands.
    """
    if request.mode == "paper":
        return ApprovalDecision(
            decision="approved",
            decided_by="auto",
            decided_at=datetime.now(UTC),
        )
    raise NotImplementedError(
        "live approval queue is wired in Phase 7; "
        "Phase 4 only supports mode=paper"
    )


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
    "request_approval",
]
